"""Abre cada URL de post/reel do Instagram, rola até o fim da seção de
comentários (ou até atingir um limite de segurança) e salva o HTML.

A conversão do HTML para CSV fica em outro script (converter_csv.py).
Rode este primeiro para gerar os HTMLs, depois o de conversão.
"""

import time
from pathlib import Path

PERFIL_FIREFOX = #aqui você coloca seu perfil do firefox que está com uma conta de instagram logada preferencialmente
ARQUIVO_URLS = "urls.txt" #arquivo de txt com as urls que quer acessar
PASTA_HTML = Path("htmls") #pasta para salvamento dos dados em formato HTML

TIMEOUT_COMENTARIOS = 25        # segundos esperando o primeiro comentário aparecer na página
PAUSA_ENTRE_ROLAGENS = 1.5      # segundos entre cada rolagem (dar tempo do Instagram carregar)
TENTATIVAS_SEM_MUDANCA = 4      # rolagens seguidas sem novo comentário até considerar "fim"
PAUSA_APOS_CLIQUE = 0.8
PASSO_ROLAGEM = 800             # pixels por rolagem (rola em passos, não direto pro fim)

# Limites de segurança por URL. Use None para desativar um deles.
LIMITE_MAX_COMENTARIOS = 3000       # para de rolar ao atingir esse total na tela
LIMITE_MAX_TEMPO_SEGUNDOS = 120     # para de rolar após esse tempo nesta URL (2 min)

# Termos de botões que DEVEM ser clicados (carregam mais comentários de nível principal).
TERMOS_CARREGAR_MAIS = (
    "carregar mais coment", "ver mais coment", "load more comment",
)
# Termos que NUNCA devem ser clicados (abririam respostas de um comentário específico).
TERMOS_IGNORAR_CLIQUE = (
    "resposta", "reply", "replies", "traduç", "translat",
)

MOTIVOS_PARADA = {
    "fim_dos_comentarios": "chegou ao fim da seção de comentários",
    "limite_de_comentarios": "atingiu o limite máximo de comentários",
    "limite_de_tempo": "atingiu o limite máximo de tempo nesta URL",
    "erro_dom": "interrompido por erro repetido ao acessar o painel de comentários",
}


def _esperar_comentarios(driver, timeout: int = TIMEOUT_COMENTARIOS) -> None:
    """Espera o primeiro link de comentário '/p/<post>/c/<id>' aparecer na página."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/c/']"))
    )


def _clicar_carregar_mais(driver) -> bool:
    """Clica em botões de 'carregar mais comentários', evitando 'ver respostas'.

    Procura em toda a página (esse botão costuma ficar no topo da lista,
    fora do que já está visível). Retorna True se algum clique foi feito.
    """
    js = r"""
    const termosPermitidos = arguments[0].map(t => t.toLowerCase());
    const termosProibidos = arguments[1].map(t => t.toLowerCase());
    const candidatos = document.querySelectorAll('button, div[role="button"]');
    for (const el of candidatos) {
        const texto = (el.innerText || el.textContent || '').toLowerCase();
        if (!texto) continue;
        if (termosProibidos.some(t => texto.includes(t))) continue;
        if (termosPermitidos.some(t => texto.includes(t))) {
            el.scrollIntoView({block: 'center'});
            el.click();
            return true;
        }
    }
    return false;
    """
    return bool(driver.execute_script(js, list(TERMOS_CARREGAR_MAIS), list(TERMOS_IGNORAR_CLIQUE)))


def _detectar_alvo_rolagem(driver):
    """Descobre ONDE os comentários rolam nesta página específica.

    O Instagram varia: às vezes os comentários abrem num painel com scroll
    próprio (comum quando aberto como modal a partir do feed), às vezes é a
    página inteira que rola (comum ao abrir a URL do post/reel direto).

    Sobe no DOM a partir de um link de comentário '/p/<post>/c/<id>' e
    procura o primeiro ancestral com scroll de verdade (overflow-y
    auto/scroll e conteúdo maior que a área visível), parando antes de
    chegar em <html>/<body> — que representariam a página inteira.

    Retorna o elemento do painel, ou None se for a página inteira mesmo.
    """
    js = r"""
    const links = document.querySelectorAll('a[href*="/c/"]');
    for (const link of links) {
        let el = link.parentElement;
        while (el && el !== document.documentElement && el !== document.body) {
            const style = window.getComputedStyle(el);
            const rolavel = (style.overflowY === 'auto' || style.overflowY === 'scroll');
            if (rolavel && el.scrollHeight > el.clientHeight + 40) {
                return el;
            }
            el = el.parentElement;
        }
    }
    return null;
    """
    return driver.execute_script(js)


def _rolar_incremento(driver, alvo, incremento: int) -> None:
    if alvo is not None:
        driver.execute_script("arguments[0].scrollTop += arguments[1];", alvo, incremento)
    else:
        driver.execute_script("window.scrollBy(0, arguments[0]);", incremento)


def _posicao_atual(driver, alvo) -> int:
    if alvo is not None:
        return driver.execute_script("return arguments[0].scrollTop;", alvo)
    return driver.execute_script("return window.pageYOffset || document.documentElement.scrollTop;")


def _altura_total(driver, alvo) -> int:
    if alvo is not None:
        return driver.execute_script("return arguments[0].scrollHeight;", alvo)
    return driver.execute_script("return document.body.scrollHeight;")


def _contar_comentarios(driver) -> int:
    return driver.execute_script(
        "return document.querySelectorAll('a[href*=\"/c/\"]').length;"
    )


def rolar_ate_o_fim(driver) -> tuple[int, str]:
    """Rola até a seção de comentários parar de crescer (ou atingir um limite).

    Primeiro descobre se há um painel de comentários com scroll próprio ou
    se é a página inteira, e rola só esse alvo. Rola em passos, checando a
    cada passo se novos comentários '/c/<id>' apareceram, e tenta clicar em
    'carregar mais comentários' quando esse botão existir. Interrompe mais
    cedo se atingir LIMITE_MAX_COMENTARIOS ou LIMITE_MAX_TEMPO_SEGUNDOS.

    Se o Instagram substituir o elemento do painel no meio da rolagem
    (comum em apps React, que re-renderizam o DOM), o alvo é redetectado
    em vez de travar numa referência que não existe mais.

    Retorna (total_de_comentarios_na_tela, motivo_da_parada).
    """
    from selenium.common.exceptions import WebDriverException

    alvo = _detectar_alvo_rolagem(driver)
    print(f"  (rolando: {'painel próprio de comentários' if alvo is not None else 'página inteira'})")

    inicio = time.monotonic()
    tentativas_sem_mudanca = 0
    ultima_contagem = _contar_comentarios(driver)
    erros_seguidos = 0
    MAX_ERROS_SEGUIDOS = 5

    while tentativas_sem_mudanca < TENTATIVAS_SEM_MUDANCA:
        if LIMITE_MAX_COMENTARIOS is not None and ultima_contagem >= LIMITE_MAX_COMENTARIOS:
            return ultima_contagem, "limite_de_comentarios"

        if (
            LIMITE_MAX_TEMPO_SEGUNDOS is not None
            and (time.monotonic() - inicio) >= LIMITE_MAX_TEMPO_SEGUNDOS
        ):
            return ultima_contagem, "limite_de_tempo"

        try:
            clicou = _clicar_carregar_mais(driver)
            if clicou:
                time.sleep(PAUSA_APOS_CLIQUE)

            _rolar_incremento(driver, alvo, PASSO_ROLAGEM)
            time.sleep(PAUSA_ENTRE_ROLAGENS)

            contagem_atual = _contar_comentarios(driver)
            posicao = _posicao_atual(driver, alvo)
            altura = _altura_total(driver, alvo)
            erros_seguidos = 0
        except WebDriverException as erro:
            # O alvo pode ter sido substituído pelo Instagram no meio da
            # rolagem (re-render). Redetecta e tenta de novo, até um limite.
            erros_seguidos += 1
            print(f"  ⚠ Elemento de rolagem perdido, redetectando... ({erros_seguidos}/{MAX_ERROS_SEGUIDOS})")
            if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                print(f"  ⚠ Muitos erros seguidos, encerrando esta URL. Detalhe: {erro}")
                return ultima_contagem, "erro_dom"
            alvo = _detectar_alvo_rolagem(driver)
            continue

        # Se ainda há espaço para rolar (mais conteúdo carregando) ou
        # surgiram novos comentários, continuamos a partir daqui.
        ainda_tem_espaco = posicao < altura - 200

        if contagem_atual <= ultima_contagem and not clicou and not ainda_tem_espaco:
            tentativas_sem_mudanca += 1
        else:
            tentativas_sem_mudanca = 0
            ultima_contagem = max(ultima_contagem, contagem_atual)

    return ultima_contagem, "fim_dos_comentarios"


def main() -> None:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.common.exceptions import TimeoutException

    PASTA_HTML.mkdir(parents=True, exist_ok=True)

    if not Path(ARQUIVO_URLS).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {ARQUIVO_URLS}")

    if not Path(PERFIL_FIREFOX).exists():
        raise FileNotFoundError(
            f"Perfil do Firefox não encontrado em: {PERFIL_FIREFOX}\n"
            "Verifique o caminho certo com 'ls ~/.mozilla/firefox/' (Linux) "
            "ou digitando 'about:profiles' na barra de endereço do Firefox, "
            "e atualize a constante PERFIL_FIREFOX no topo deste arquivo.\n"
            "Além disso, feche todas as janelas do Firefox antes de rodar "
            "este script (o perfil fica travado enquanto o Firefox está aberto)."
        )

    with open(ARQUIVO_URLS, encoding="utf-8") as f:
        urls = [linha.strip() for linha in f if linha.strip()]

    options = Options()
    options.add_argument("-profile")
    options.add_argument(PERFIL_FIREFOX)

    driver = webdriver.Firefox(options=options)

    try:
        print(f"{len(urls)} URLs encontradas.")

        for indice, url in enumerate(urls, start=1):
            print("\n" + "=" * 60)
            print(f"{indice}/{len(urls)}")
            print(url)

            try:
                driver.get(url)

                try:
                    _esperar_comentarios(driver)
                except TimeoutException:
                    print("⚠ Nenhum comentário apareceu a tempo, pulando esta URL.")
                    continue

                print("Rolando até o fim dos comentários...")
                total, motivo = rolar_ate_o_fim(driver)
                print(f"✓ {total} comentários carregados ({MOTIVOS_PARADA.get(motivo, motivo)}).")

                html = driver.page_source
                nome = url.rstrip("/").split("/")[-1]
                caminho = PASTA_HTML / f"{indice:04d}_{nome}.html"
                caminho.write_text(html, encoding="utf-8")
                print(f"✓ HTML salvo: {caminho}")

            except Exception as erro:
                print(f"⚠ Erro inesperado nesta URL, pulando para a próxima. Detalhe: {erro}")
                continue

            print("→ Indo para a próxima URL...")

        print("\nTodas as páginas foram processadas.")
        print(f"Rode o script de conversão para gerar o CSV a partir de '{PASTA_HTML}/'.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
