# Verdade e direitos (ler antes de pesquisar ou escrever roteiro)

Estas regras protegem o canal e a marca do usuário. Valem mesmo se ele pedir o contrário. Nesse caso, diga em uma linha por quê e ofereça uma saída que respeite a regra.
Ideia adaptada do pacote "Heist & Dark History Studio" (2026-11-17). O texto é nosso, nada foi copiado.

## Fatos
- **Todo número, data, horário, nome e citação tem fonte.** Num vídeo informativo ou documental, crie `<projeto>/FONTES.md` com uma linha por afirmação: o que diz, de onde veio (link ou documento) e a data da consulta. Se não estiver confirmado, marque `NÃO CONFIRMADO`.
- **Nunca invente** documento, diário, depoimento, testemunha, citação, número, caso de cliente ou resultado. Se for uma lenda, diga "segundo a lenda". Se for uma estimativa, diga "cerca de".
- Para o que não tem fonte oficial, use "segundo …", "de acordo com …" ou "os investigadores acreditam que …".
- **Confira cada número duas vezes.** Se as fontes divergirem, use o número mais conservador e diga "cerca de".
- Um relatório ou alerta antigo é contexto. Só apresente como causa do que aconteceu se a fonte disser isso.
- **Comercial:** só use números de produto (tempo economizado, % de redução, nº de clientes) que vieram do usuário ou do sistema dele. Anote no `BRIEFING.md` quem deu cada número. Depoimento só se for real e autorizado. Sem isso, use cena ilustrativa e não ponha nome de pessoa.

## Pessoas
- Nunca dê nome a suspeito que não foi condenado. Diga "um homem de 39 anos", "dois suspeitos".
- Uma pessoa pública em papel público (autoridade, empresa, especialista) pode ser nomeada. A imagem dela é só por foto com licença livre (abaixo). Nunca gere o rosto dela com IA.
- Pessoa real em vídeo gerado só a partir de foto enviada pelo usuário e com autorização de imagem (regra que já existe nos agentes).
- Vítimas: sem nome, sem detalhe gráfico, sem piada.

## Imagens, vídeos e sons
- **Fontes grátis aceitas, com a licença conferida no item:**
  - Pexels e Pixabay (`buscar_stock.py`): uso comercial livre, crédito opcional.
  - Wikimedia Commons (`buscar_arquivo.py fotos`): só domínio público, CC0, CC BY e CC BY-SA. O crédito aparece **na tela e na descrição**. CC BY-SA exige crédito com o nome da licença.
  - Internet Archive (`buscar_arquivo.py filmes`): `LIVRE` só para coleções curadas ou de governo (Prelinger, FedFlix, National Archives, NASA, militares). A marca de domínio público que quem enviou põe no item (`MARCADO`) **não basta**: em 2026-11-17 apareceram séries da BBC assim. `MARCADO` e `CONFERIR` só com o usuário confirmando o dono e os direitos na página do item (`--conferido`).
  - Arquivo Nacional dos EUA (catalog.archives.gov): só com o campo **Use = Unrestricted**. Baixe pelo navegador.
- **Nunca use:** cinejornal comercial (Pathé, Movietone, Paramount), telejornal, imagem de câmera de segurança de terceiros, vídeo de turista, vídeo ou miniatura de outro canal, arte de outra pessoa, nem qualquer coisa em que a licença esteja em dúvida.
- **Descreva com honestidade:** um filme que ilustra a época não é "a filmagem daquela noite". Na legenda de crédito, escreva o que o arquivo é: "Filme do FBI, 1951 · Arquivo Nacional dos EUA".
- **Recriação:** jornal, documento ou tela que você desenhou para ilustrar um fato real recebe a marca `RECRIAÇÃO` na tela.
- Nenhuma logo, mascote ou produto de outra marca em destaque. Descreva com palavras ("a fabricante do elevador").
- Música e efeitos: só da trilha grátis com licença conferida, de trilha por IA ou da sintetizada (agente `estudio-musical`). Faixa trazida pelo usuário só se ele tiver o direito de uso.

## Créditos (entrega)
- Cada mídia de terceiros tem um `<arquivo>.credito.txt` ao lado ou uma linha em `creditos.json`, gravados pelos scripts de busca.
- O crédito curto vai **na tela** enquanto a mídia aparece (texto pequeno, canto inferior, legível). Pexels e Pixabay dispensam o crédito, mas ele pode ir mesmo assim.
- Na descrição da publicação vão todos os créditos. Confira se não falta nenhum antes de entregar.

## Título e capa
- Título e capa contam a verdade do vídeo. Ousado pode, falso não.

## Quem confere
- `estudio-roteirista`: aplica estas regras ao escrever e entrega o `FONTES.md` junto com o roteiro (quando o vídeo afirma fatos).
- `estudio-qualidade`: antes da entrega, confere roteiro × `FONTES.md` (afirmação sem fonte = reprovado), mídia × crédito na tela e na descrição, recriação marcada e ausência de logo de terceiros.
