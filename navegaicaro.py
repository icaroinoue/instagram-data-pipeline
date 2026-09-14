from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import glob

#  LISTAS

PERFIS_ALVO = [
    "guilhermefiuzaoficial",
    "gui.kilter",
    "gusgayer",
    "hertzdiaspstu",
    "historiapublica",
    "jairmessiasbolsonaro",
    "jairmearrependi",
    "jamiledavies",
    "joicehasselmannoficial",
    "jones.manoel",
    "j_kfouri",
    "juliazanattasc",
    "kimkataguiri",
    "kimpaim",
    "mylaura_m",
    "lazarorosa",
    "leandro.demori",
    "leandroruschel",
    "leosakamoto",
    "lucaspavanato",
    "luis_nassif",
    "lf_ponde",
    "lulaoficial",
    "lunazarattini",
    "magnomalta",
    "marcelvanhattem",
    "marcoantoniovillaoficial",
    "marcofeliciano",
    "mariofriasoficial",
    "michellebolsonaro",
    "miriamleitao7",
    "monica_bergamo",
    "nandomoura_oficial_101",
    "nataliabonavides",
    "nathfinancas",
    "natuzanery",
    "nikolasferreiradm",
    "pablomarcal1",
    "patacamposmello",   
]
    

HASHTAGS_ALVO = [
    
]


#  ABRE NAVEGADOR


def open_browser() -> webdriver.Firefox:
    """Open Firefox using the default-release profile (where Zeeschuimer is installed)."""
    perfis = #coloca seu perfil do firefox aqui(procure ele em about:profiles);
    if not perfis:
        raise RuntimeError("Não encontrei o perfil do Firefox. Verifique se existe um perfil default-release.")
    options = Options()
    options.add_argument("-profile")
    options.add_argument(perfis[0])
    print(" Usando perfil do Firefox")
    return webdriver.Firefox(options=options)


# FUNÇÕES DE COLETA

def coletar_perfis(driver: webdriver.Firefox):
    """Scroll through each profile in PERFIS_ALVO."""
    print(f"\n {len(PERFIS_ALVO)} perfis na lista\n")

    total_perfis = len(PERFIS_ALVO)
    for idx, perfil in enumerate(PERFIS_ALVO, start=1):
        print(f"\n Perfil {idx}/{total_perfis} · @{perfil}")
        driver.get(f"https://www.instagram.com/{perfil}/")
        time.sleep(2)

        for i in range(10):
            print(f"   Scroll {i+1}/10")
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(1)
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)

        print(f"   @{perfil} finalizado")


def coletar_hashtags(driver: webdriver.Firefox):
    """Scroll through each hashtag in HASHTAGS_ALVO."""
    print(f"\n {len(HASHTAGS_ALVO)} hashtags na lista\n")

    total_hashtags = len(HASHTAGS_ALVO)
    for idx, hashtag in enumerate(HASHTAGS_ALVO, start=1):
        print(f"\n Hashtag {idx}/{total_hashtags} · #{hashtag}")
        driver.get(f"https://www.instagram.com/explore/tags/{hashtag}/")
        time.sleep(4)

        for i in range(25):
            print(f"   Scroll {i+1}/25")

            times = driver.find_elements(By.TAG_NAME, "time")
            for t in times:
                timestamp = t.get_attribute("datetime")
                if timestamp:
                    print(f"    #{hashtag} → {timestamp}")

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        print(f"  #{hashtag} finalizada")


def coletar_ambos(driver: webdriver.Firefox):
    """Run profiles first, then hashtags."""
    coletar_perfis(driver)
    coletar_hashtags(driver)


#  MENU


MENU = """
╔══════════════════════════════════════╗
║     Instagram Coleta — MDA          ║
╠══════════════════════════════════════╣
║  1 · Perfis                         ║
║  2 · Hashtags                       ║
║  3 · Perfis + Hashtags              ║
╚══════════════════════════════════════╝
"""

OPCOES = {
    "1": ("Perfis", coletar_perfis),
    "2": ("Hashtags", coletar_hashtags),
    "3": ("Perfis + Hashtags", coletar_ambos),
}


def instagram_coleta():
    print(MENU)

    escolha = input("Escolha uma opção (1/2/3): ").strip()
    if escolha not in OPCOES:
        print(" Opção inválida. Execute o script novamente.")
        return

    nome_opcao, funcao_coleta = OPCOES[escolha]
    print(f"\n  Modo selecionado: {nome_opcao}")


    driver = open_browser()

    try:
        funcao_coleta(driver)
        print("\n Coleta finalizada!")

    except Exception as e:
        print(f"\n Erro: {e}")

    finally:
        input("\nPressione Enter para fechar o navegador...")
        driver.quit()


if __name__ == "__main__":
    instagram_coleta()
