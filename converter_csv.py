"""Lê os HTMLs salvos por capturar_comentarios.py e gera o CSV de comentários.

Roda independente da coleta: pode ser executado quantas vezes quiser sobre
a mesma pasta de HTMLs, sem precisar reabrir o navegador.

Otimizado para velocidade em páginas com muitos comentários:
- usa o parser 'lxml' (bem mais rápido que o 'html.parser' padrão)
- sobe uma profundidade fixa no DOM para achar o container do comentário,
  em vez de escanear links a cada nível subido
- calcula a contagem de respostas numa segunda passada separada, só nos
  trechos que têm a palavra "resposta", em vez de extrair o texto do
  container inteiro de cada comentário
"""

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

PASTA_HTML = Path("htmls")
ARQUIVO_CSV = Path("comentarios.csv")

# Parser mais rápido; cai para o padrão do Python se o pacote lxml não
# estiver instalado (`pip install lxml`).
try:
    import lxml  # noqa: F401
    PARSER_HTML = "lxml"
except ImportError:
    PARSER_HTML = "html.parser"

COLUNAS = [
    "post_comment_id",
    "parent_comment_original_id",
    "post_original_id",
    "comment_description",
    "comment_published_at",
    "comment_original_id",
    "comment_author_username",
    "comment_replies_count",
    "comment_likes_count",
]

PADRAO_LINK_COMENTARIO = re.compile(r"^/p/([^/]+)/c/(\d+)/?$")
PADRAO_USUARIO = re.compile(r"^/([A-Za-z0-9._]+)/?$")
PADRAO_CURTIDAS = re.compile(r"([\d.,]+)\s+curtida(?:s)?", re.IGNORECASE)
PADRAO_RESPOSTAS = re.compile(
    r"(?:ver\s+(?:todas\s+as\s+)?|ocultar\s+)?([\d.,]+)\s+resposta(?:s)?",
    re.IGNORECASE,
)

TERMOS_IGNORADOS = {"Responder", "Curtir", "Verificado", "Seguir", "Ocultar", "Denunciar"}

NIVEIS_CONTAINER = 12       # teto de segurança; normalmente para bem antes por causa do "limit=2"
NIVEIS_PARENT_ID = 8        # profundidade máxima buscando o comentário-pai
NIVEIS_BLOCO_RESPOSTA = 10  # profundidade máxima buscando o comentário dono de uma "resposta"


def numero_instagram(valor: Optional[str]) -> int:
    """Converte valores do Instagram ('48.742', '9.082', '1,2 mil') para inteiro."""
    if not valor:
        return 0
    texto = str(valor).strip().lower().replace("\xa0", " ")
    multiplicador = 1
    if "mil" in texto:
        multiplicador = 1_000
        texto = texto.replace("mil", "").strip()
    elif "mi" in texto:
        multiplicador = 1_000_000
        texto = texto.replace("mi", "").strip()

    if multiplicador > 1:
        texto = texto.replace(".", "").replace(",", ".")
        try:
            return int(float(texto) * multiplicador)
        except ValueError:
            return 0

    somente_digitos = re.sub(r"\D", "", texto)
    return int(somente_digitos) if somente_digitos else 0


def achar_container(link_data: Tag, max_niveis: int = NIVEIS_CONTAINER) -> Tag:
    """Sobe no DOM até o container do comentário, parando de forma barata.

    Sobe enquanto o ancestral ainda contiver só o link deste comentário
    (checagem rápida por 'limit=2', sem extrair texto). Assim que aparece
    outro comentário no mesmo nível, para — evita "vazar" para o container
    de um comentário vizinho ou do pai, o que aconteceria com uma subida
    de profundidade totalmente fixa. É mais barato que o método original
    porque não faz mais a varredura de texto ("Responder") a cada nível.
    """
    melhor = link_data.parent if isinstance(link_data.parent, Tag) else link_data
    atual = melhor

    for _ in range(max_niveis):
        pai = atual.parent
        if not isinstance(pai, Tag):
            break
        # limit=2: só precisamos saber se há MAIS de um link de comentário aqui.
        links = pai.find_all("a", href=PADRAO_LINK_COMENTARIO, limit=2)
        if len(links) > 1:
            break
        melhor = pai
        atual = pai

    return melhor


def achar_username(container: Tag, link_data: Tag) -> str:
    for a in container.find_all("a", href=True):
        if a is link_data:
            continue
        href = a.get("href", "")
        match = PADRAO_USUARIO.match(href)
        if match and not href.startswith("/p/"):
            username = match.group(1)
            if username not in {"explore", "accounts", "direct", "reels"}:
                return username
    return ""


def achar_descricao(container: Tag, username: str) -> str:
    candidatos: list[str] = []
    for span in container.find_all("span", attrs={"dir": "auto"}):
        texto = span.get_text(" ", strip=True)
        if not texto or texto == username or texto in TERMOS_IGNORADOS:
            continue
        if PADRAO_CURTIDAS.search(texto) or PADRAO_RESPOSTAS.search(texto):
            continue
        if re.fullmatch(r"\d+\s*[smhd]|\d+\s*(?:sem|d)", texto, re.IGNORECASE):
            continue
        candidatos.append(texto)
    return max(candidatos, key=len) if candidatos else ""


def achar_parent_id(link_data: Tag, comment_id: str, niveis: int = NIVEIS_PARENT_ID) -> str:
    atual: Optional[Tag] = link_data
    for _ in range(niveis):
        atual = atual.parent if isinstance(atual, Tag) else None
        if not isinstance(atual, Tag):
            break

        ids: list[str] = []
        for link in atual.find_all("a", href=PADRAO_LINK_COMENTARIO):
            match = PADRAO_LINK_COMENTARIO.match(link.get("href", ""))
            if match and match.group(2) not in ids:
                ids.append(match.group(2))

        # Agrupador pequeno: primeiro ID tende a ser o comentário principal.
        if 2 <= len(ids) <= 25 and comment_id in ids:
            primeiro = ids[0]
            if primeiro != comment_id:
                return primeiro

    return ""


def preencher_contagem_respostas(soup: BeautifulSoup, linhas: list[dict[str, object]]) -> None:
    """Segunda passada: associa 'X respostas' ao comentário-pai mais próximo.

    Só examina trechos que já contêm a palavra "resposta", em vez de
    extrair o texto de todo container de comentário — bem mais barato em
    páginas com milhares de comentários.
    """
    for tag in soup.find_all(["span", "div"], attrs={"dir": "auto"}):
        texto = tag.get_text(" ", strip=True)
        if "resposta" not in texto.lower():
            continue

        match = PADRAO_RESPOSTAS.search(texto)
        if not match:
            continue
        qtd_respostas = numero_instagram(match.group(1))
        if qtd_respostas <= 0:
            continue

        atual: Optional[Tag] = tag
        for _ in range(NIVEIS_BLOCO_RESPOSTA):
            atual = atual.parent if isinstance(atual, Tag) else None
            if not isinstance(atual, Tag):
                break

            links = atual.find_all("a", href=PADRAO_LINK_COMENTARIO)
            if not links:
                continue

            ids_no_bloco: list[str] = []
            for link in links:
                match_id = PADRAO_LINK_COMENTARIO.match(link.get("href", ""))
                if match_id and match_id.group(2) not in ids_no_bloco:
                    ids_no_bloco.append(match_id.group(2))

            # O comentário-pai é o primeiro da lista que ainda não tem parent_id.
            for linha in linhas:
                if (
                    linha["comment_original_id"] in ids_no_bloco
                    and not linha["parent_comment_original_id"]
                ):
                    if linha["comment_replies_count"] == 0:
                        linha["comment_replies_count"] = qtd_respostas
                    break
            break


def extrair_comentarios_html(caminho_html: Path) -> list[dict[str, object]]:
    try:
        conteudo = caminho_html.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(conteudo, PARSER_HTML)
    except Exception as erro:
        print(f"Erro ao ler {caminho_html.name}: {erro}")
        return []

    linhas: list[dict[str, object]] = []
    vistos: set[str] = set()

    for link_data in soup.find_all("a", href=PADRAO_LINK_COMENTARIO):
        match = PADRAO_LINK_COMENTARIO.match(link_data.get("href", ""))
        if not match:
            continue

        post_original_id, comment_id = match.group(1), match.group(2)
        if comment_id in vistos:
            continue
        vistos.add(comment_id)

        container = achar_container(link_data)
        username = achar_username(container, link_data)
        descricao = achar_descricao(container, username)

        time_tag = container.find("time")
        publicado_em = ""
        if time_tag and time_tag.has_attr("datetime"):
            raw_dt = time_tag["datetime"]
            try:
                dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                publicado_em = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                publicado_em = raw_dt

        parent_id = achar_parent_id(link_data, comment_id)

        texto_container = container.get_text(" ", strip=True)
        match_curtidas = PADRAO_CURTIDAS.search(texto_container)

        linhas.append({
            "post_comment_id": "",
            "parent_comment_original_id": parent_id,
            "post_original_id": post_original_id,
            "comment_description": descricao,
            "comment_published_at": publicado_em,
            "comment_original_id": comment_id,
            "comment_author_username": username,
            "comment_replies_count": 0,  # preenchido em preencher_contagem_respostas
            "comment_likes_count": numero_instagram(match_curtidas.group(1)) if match_curtidas else 0,
        })

    preencher_contagem_respostas(soup, linhas)
    return linhas


def atualizar_csv(pasta_html: Path = PASTA_HTML, arquivo_csv: Path = ARQUIVO_CSV) -> int:
    """Processa todos os HTMLs e recria um CSV único, removendo duplicatas."""
    todas: dict[str, dict[str, object]] = {}
    arquivos = sorted(pasta_html.glob("*.html"))

    if not arquivos:
        print("Nenhum arquivo HTML encontrado para processar.")
        return 0

    print(f"Processando {len(arquivos)} arquivos HTML (parser: {PARSER_HTML})...")

    for caminho in arquivos:
        try:
            for linha in extrair_comentarios_html(caminho):
                todas[str(linha["comment_original_id"])] = linha
            print(f"✓ Extraído: {caminho.name}")
        except Exception as erro:
            print(f"Erro ao processar {caminho.name}: {erro}")

    with arquivo_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(todas.values())

    print(f"✓ CSV atualizado: {arquivo_csv} ({len(todas)} registros)")
    return len(todas)


if __name__ == "__main__":
    atualizar_csv()
