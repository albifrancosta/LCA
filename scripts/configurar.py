"""Assistente de configuração das chaves de API — rode no SEU terminal, fora do chat.

  python configurar.py              → passa por cada chave, mostra o que ela libera e o custo,
                                      pede o valor com a digitação ESCONDIDA, testa (só as que têm teste grátis)
                                      e grava no .env da skill
  python configurar.py GEMINI_API_KEY FAL_KEY   → só essas
  python configurar.py --remover FAL_KEY        → apaga uma chave do .env

A chave nunca aparece na tela, no chat nem em log. O .env fica só no seu computador (está no .gitignore).
Este script se recusa a rodar sem um terminal interativo — o Claude não deve rodá-lo por você.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chaves  # noqa: E402


def terminal_interativo():
    """True só com uma pessoa num terminal de verdade. No Windows, NUL e pipes passam no isatty(),
    por isso confere se a entrada é um console (GetConsoleMode)."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
        if os.name == "nt":
            import ctypes
            import msvcrt
            modo = ctypes.c_uint()
            h = msvcrt.get_osfhandle(sys.stdin.fileno())
            return bool(ctypes.windll.kernel32.GetConsoleMode(h, ctypes.byref(modo)))
        return True
    except (OSError, ValueError, AttributeError):
        return False


def _nome_da_linha(linha):
    if "=" not in linha or linha.lstrip().startswith("#"):
        return None
    nome = linha.split("=", 1)[0].strip()
    if nome.startswith("export "):
        nome = nome[7:].strip()
    return nome


def gravar(caminho, novos, remover=()):
    """Atualiza/insere NOME=valor no .env preservando comentários e outras linhas."""
    linhas = []
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8-sig") as f:
            linhas = f.read().splitlines()
    feitos, saida = set(), []
    for linha in linhas:
        nome = _nome_da_linha(linha)
        if nome in remover:
            continue
        if nome in novos:
            saida.append(f"{nome}={novos[nome]}")
            feitos.add(nome)
        else:
            saida.append(linha)
    for nome, v in novos.items():
        if nome not in feitos:
            saida.append(f"{nome}={v}")
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(saida).strip() + "\n")
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    caminho = chaves.caminho_env()
    if args[:1] == ["--remover"]:
        gravar(caminho, {}, remover=set(args[1:]))
        print(f"Removido(s) de {caminho}: {', '.join(args[1:]) or 'nada'}")
        return
    if not terminal_interativo():
        sys.exit("Este assistente precisa de um terminal interativo. Abra um terminal e rode:\n"
                 f"  python \"{os.path.abspath(__file__)}\"\n(Não cole chaves no chat.)")
    alvo = [a for a in args if a in chaves.CHAVES] or list(chaves.CHAVES)
    existentes = chaves.ler_env(caminho)
    chaves.carregar()
    print("Configuração das chaves de API — a digitação fica escondida e nada vai para o chat.")
    print("Todas são opcionais: sem nenhuma, a skill já faz motion graphics, edição, legendas e montagem.")
    print("Enter vazio = pular (mantém a atual, se houver).\n")
    novos = {}
    for nome in alvo:
        c = chaves.CHAVES[nome]
        ja = "já configurada" if (existentes.get(nome) or os.environ.get(nome)) else "não configurada"
        print(f"— {c['nome']} · {chaves.ROTULO[c['custo']]} · {ja}")
        print(f"  libera: {c['libera']}")
        print(f"  custo: {c['preco']}")
        print(f"  crie em: {c['criar']}")
        try:
            v = getpass.getpass(f"  cole a {nome} (escondida) e Enter: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado — nada foi gravado.")
            return
        if not v:
            print("  pulada.\n")
            continue
        r = chaves.testar(nome, v)
        if r.startswith("recusada"):
            print(f"  ⚠️ teste: {r}. Não gravei — confira a chave e rode de novo.\n")
            continue
        print(f"  teste: {r}\n")
        novos[nome] = v
    if novos:
        gravar(caminho, novos)
        print(f"✅ Gravado em {caminho}: {', '.join(novos)} (os valores não são mostrados).")
    else:
        print("Nada novo para gravar.")
    print("Pronto. No chat, peça: \"confere minhas chaves\" — o Claude roda `chaves.py status` e só vê se elas existem.")


if __name__ == "__main__":
    main()
