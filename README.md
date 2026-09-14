# Pipeline de Coleta e Extração de Comentários do Instagram

> Automação em Python desenvolvida no âmbito de Iniciação Científica para superar limitações de extração profunda em interfaces dinâmicas, viabilizando análises de dados estruturados para a equipe de pesquisa.

---

## 💡 O Contexto e a Motivação

Durante as etapas de coleta da nossa pesquisa, utilizávamos ferramentas como a extensão Zeeschuimer acoplada à navegação automatizada para registrar postagens. No entanto, surgiu um desafio central: **essas ferramentas não coletavam a seção de comentários**, e os scripts iniciais disponíveis não realizavam a rolagem autônoma nem o salvamento dos dados.

Fazer a extração manual de milhares de interações inviabilizaria o cronograma e traria inconsistências. Diante dessa necessidade, assumi o desenvolvimento de uma solução própria: implementei um fluxo autônomo capaz de lidar com a rolagem assíncrona da interface do Instagram, persistir as páginas brutas com segurança e, em seguida, processar todo o volume em uma base tabular estruturada (CSV) para que a outra equipe de pesquisa pudesse conduzir as análises.

---

## ⚙️ Como o Pipeline Funciona

Para tornar a coleta confiável e rápida, optei por desacoplar o processo em etapas independentes: 

[ navega.py ]               → Navegação contínua por perfis e tags (integração Zee)
↓
[ capturar_comentarios.py ] → Scroll adaptativo + cliques em "carregar mais" + dump HTML
↓
[ converter_csv.py ]        → Parsing off-line em massa via lxml/Regex → CSV limpo


### 1. Navegação Automatizada (`navega.py`)
Script que auxiliei a estruturar para automatizar o trânsito entre perfis-alvo e hashtags, mantendo sessões persistentes via perfil do Firefox para viabilizar a captura de metadados das publicações.

### 2. Captura Autônoma e Resiliente (`capturar_comentarios.py`)
* **Detecção Dinâmica do Alvo de Scroll:** O Instagram ora rola a janela inteira, ora utiliza um contêiner interno com `overflow-y` (modal). O script identifica via JavaScript exatamente qual elemento deve receber o evento de rolagem.
* **Scroll em Passos e Cliques Inteligentes:** Realiza descidas incrementais e clica automaticamente em botões como *"carregar mais comentários"*, ignorando propositalmente botões de *"ver respostas"* para evitar loops desnecessários.
* **Tolerância a Falhas de Re-renderização:** Como a interface é construída em React, contêineres podem ser destruídos e recriados durante o scroll. O código trata exceções de DOM e redetecta o alvo em tempo real sem abortar o processo.
* **Salvamento Desacoplado:** Armazena o `page_source` íntegro em arquivos `.html`, garantindo que os dados brutos estejam salvos mesmo se a conexão cair.

### 3. Parsing e Normalização em Larga Escala (`converter_csv.py`)
* **Processamento Offline:** Lê a pasta de HTMLs sem abrir o navegador, permitindo reexecutar o tratamento de texto quantas vezes for necessário.
* **Performance com `lxml`:** Utiliza parser C otimizado, essencial para lidar com páginas contendo milhares de nós de comentários.
* **Mapeamento Hierárquico:** Extrai usuário, descrição, data de publicação, curtidas e associa respostas ao comentário-pai correspondente via expressões regulares.
* **Entrega:** Consolida tudo em um único arquivo `comentarios.csv` higienizado e pronto para consumo em ferramentas de BI, planilhas ou bibliotecas de análise (como Pandas).

---

## 🛠️ Tecnologias e Ferramentas

* **Linguagem:** Python 3
* **Automação Web:** Selenium WebDriver (Firefox Profile)
* **Extração e Parsing:** BeautifulSoup4 & lxml
* **Manipulação de Padrões:** Expressões Regulares (`re`)
* **Formato de Saída:** CSV estruturado (UTF-8 com BOM para compatibilidade com Excel)

---

2. Configuração

    No script capturar_comentarios.py, ajuste a variável PERFIL_FIREFOX com o caminho do seu perfil local do navegador (encontrado em about:profiles no Firefox).

    Crie um arquivo urls.txt na raiz contendo um link de postagem por linha.

3. Execução

Execute a captura das páginas:
Bash

python capturar_comentarios.py

Após o término, processe os arquivos baixados e gere o arquivo consolidado:
Bash

python converter_csv.py

O resultado final será salvo automaticamente como comentarios.csv.


📌 Aprendizados e Contribuições

Mais do que apenas escrever código de scraping, esse projeto me permitiu:

    Resolver um gargalo operacional real da equipe de pesquisa, transformando um processo inviável de coleta manual em uma rotina automatizada e auditável.

    Compreender a fundo os desafios de interfaces modernas reativas (renderização dinâmica, scrolls assíncronos e nós voláteis no DOM).

    Aplicar na prática o desacoplamento de software: separar a fase de ingestão (I/O intensiva de rede) da fase de transformação (processamento de dados e texto), aumentando drasticamente a velocidade de entrega do conjunto de dados final.