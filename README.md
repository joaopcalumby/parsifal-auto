# parsifal-auto

Ferramenta de linha de comando para a triagem de estudos de revisões sistemáticas feitas no
[Parsifal](https://parsif.al). Serve para qualquer tema: o vocabulário da revisão fica num arquivo de
configuração, não no código.

A ferramenta supõe uma seleção em três etapas, e os critérios cadastrados no Parsifal seguem esse
prefixo (`ETAPA 1 - ...`, `ETAPA 2 - ...`):

| Etapa | O que se lê | Quem decide |
|---|---|---|
| ETAPA 1 | título, palavras-chave e resumo | você, com apoio desta ferramenta |
| ETAPA 2 | introdução e resumo | você, à mão |
| ETAPA 3 | texto completo | você, à mão |

A ferramenta só atua na ETAPA 1. Ela lê os estudos importados na revisão, aponta quais merecem
atenção e por quê, e depois marca no Parsifal como aceito ou rejeitado **o que você decidiu**, com o
critério anexado. É o mesmo que você faria abrindo artigo por artigo e clicando.

## Requisitos

- **Python 3.13.** É a versão em que o projeto foi desenvolvido e em que os testes passam.
- Uma conta no Parsifal com acesso à revisão a triar: dona da revisão ou colaboradora dela.
- Os estudos já importados na revisão (aba *Conducting > Import Studies* do Parsifal).

## Instalação

Da raiz do repositório:

```bash
python -m venv .venv
```

Se a máquina tiver mais de um Python, no Windows escolha a versão pelo launcher:
`py -3.13 -m venv .venv`.

Ative o ambiente:

| Terminal | Comando |
|---|---|
| PowerShell | `.venv\Scripts\Activate.ps1` |
| Git Bash | `source .venv/Scripts/activate` |
| Linux / macOS | `source .venv/bin/activate` |

E instale as dependências:

```bash
pip install -r requirements.txt
```

Para conferir a instalação, rode os testes. Eles não acessam a rede:

```bash
python -m pytest
```

## Configuração

1. Copie `.env.example` para `.env`.
2. Em `PARSIFAL_REVIEW_URL`, cole a URL da revisão como aparece no navegador, **sem barra final**.
   O formato é `https://parsif.al/<usuario>/<slug-da-revisao>`.
3. Preencha `PARSIFAL_USERNAME` e `PARSIFAL_PASSWORD`. A automação loga sozinha e reloga quando a
   sessão cai.

Se preferir não guardar a senha no arquivo, deixe usuário e senha vazios e preencha
`PARSIFAL_SESSIONID` e `PARSIFAL_CSRFTOKEN` com os cookies de uma sessão aberta no navegador
(DevTools > Application > Cookies > parsif.al). Nesse caminho, quando o cookie expira é preciso
copiar de novo.

O `.env` está no `.gitignore` e não sai da máquina.

### A revisão no `config/revisoes.json`

Copie `config/revisoes.exemplo.json` para `config/revisoes.json` e descreva nele a sua revisão. Como o
`.env`, o `revisoes.json` está no `.gitignore`: o repositório traz só o exemplo.

Cada revisão é um bloco identificado por uma sigla (`A`, `B`...). O exemplo usa um tema fictício,
aprendizado federado em dispositivos de borda:

```json
"A": {
  "nome": "Aprendizado federado em dispositivos de borda",
  "criterio_de_aceite": "ETAPA 1 - Estudo trata de aprendizado federado",
  "termos_dominio": ["federated learning", "federated training", "fedavg"],
  "siglas_ambiguas": ["fl"],
  "termos_colisao": ["fuzzy", "membership function"],
  "termos_recorte": ["edge device", "edge devices", "iot"]
}
```

| Chave | O que é |
|---|---|
| `nome` | só para exibição |
| `criterio_de_aceite` | critério usado quando você aceita sem escrever critério. Precisa ser o texto exato de um critério de inclusão cadastrado no Parsifal |
| `termos_dominio` | termos que, sozinhos, provam que o estudo é do tema |
| `siglas_ambiguas` | siglas do tema que também nomeiam outra coisa. Contam como termo do tema, mas não como prova |
| `termos_colisao` | vocabulário da área com que a sigla colide |
| `termos_recorte` | termos que delimitam a revisão dentro do tema (população, contexto, nível) |

Os termos são em inglês, como os resumos, e casam como palavra inteira, sem diferenciar maiúscula.
**Todas as chaves de termos são opcionais**: lista vazia ou ausente desliga o sinal correspondente.
Vale repetir os mesmos termos de domínio em vários blocos quando as revisões são do mesmo tema e
mudam só no recorte, como os blocos `A` e `B` do exemplo.

**A revisão é escolhida em dois lugares, e os dois precisam concordar:**

| Onde | O que decide | Usado por |
|---|---|---|
| `PARSIFAL_REVIEW_URL` no `.env` | com qual revisão do Parsifal a automação conversa | `verificar`, `baixar`, `completar`, `aplicar` |
| `--revisao` na linha de comando | qual bloco do `config/revisoes.json` vale | `classificar`, `aplicar` |

Se o `.env` aponta para a revisão B e o comando diz `--revisao A`, a automação baixa os estudos da
revisão B e procura neles os termos de recorte da A. Nada avisa: a planilha sai coerente e errada. O `--revisao` tem `A` como padrão, então esquecê-lo também não dá erro.

## Uso

Com o ambiente ativado, da raiz do repositório:

```bash
python -m triagem verificar                # sonda a revisão, não escreve nada
python -m triagem baixar                   # copia os estudos para dados/estudos.csv
python -m triagem completar                # busca fora o resumo que o Parsifal não tem
python -m triagem classificar --revisao A  # gera dados/decisoes.xlsx
#   abra a planilha e decida: 'aceitar' ou 'rejeitar' na coluna 'acao'
python -m triagem aplicar --revisao A              # simulação: mostra o que seria escrito
python -m triagem aplicar --revisao A --confirmar  # grava no Parsifal
```

**Comece sempre por `verificar`** e confira se a primeira linha impressa (`revisão:`) é a URL que
você quer.

> **A escrita no Parsifal ainda não foi testada ao vivo.** Leitura e login foram verificados contra
> uma revisão real, mas nenhum `aplicar --confirmar` foi enviado até agora. Na primeira vez, deixe
> só **uma** linha preenchida na coluna `acao`, rode `aplicar --confirmar` e confira na tela do
> Parsifal se o status e o critério entraram e se o resto do artigo (resumo, autores, DOI) continua
> intacto. Só depois aplique o resto.

Detalhes de cada comando:

- **`baixar`** faz uma requisição por artigo e demora. A instância hospedada do Parsifal não tem
  export: resumo e palavras-chave só existem na tela de cada artigo. Só os artigos ainda
  `Unclassified` são baixados. Use `--limite N` para testar com poucos e `--pausa` para ajustar o
  intervalo entre requisições (padrão 0,3 s).
- **`classificar`** ignora estudo que já tem status no Parsifal, então rodar duas vezes não desfaz
  trabalho. Aceita `--entrada` para ler um `.csv` ou `.bib` no lugar de `dados/estudos.csv`.
- **`aplicar`** sem `--confirmar` nunca escreve.

Todos os comandos aceitam `--help`.

### Antes de trocar de revisão

A pasta `dados/` é uma só para todas as revisões: `baixar` sobrescreve o `estudos.csv`, e
`classificar` remonta o `decisoes.xlsx` só com os estudos da revisão nova. **Decisão escrita na
planilha e ainda não aplicada some.** Rode `aplicar --confirmar` antes da troca, ou copie a pasta
(por exemplo, para `dados-A/`).

Para trocar: edite `PARSIFAL_REVIEW_URL` no `.env`, rode `verificar` e use a sigla certa no
`--revisao`.

## A planilha de trabalho

`dados/decisoes.xlsx`. É XLSX e não CSV porque traz filtro e busca por coluna, que é o que falta na
tela do Parsifal.

| Coluna | De quem é |
|---|---|
| **`acao`** | **sua.** Escreva `aceitar` ou `rejeitar`. Vazio quer dizer "ainda não decidi" |
| **`criterio`** | **sua.** O texto do critério. A aba `criterios` da planilha tem a lista pronta, lida do Parsifal |
| `sugestao`, `sinais`, `notas_etapa_2`, `recorte_em` | da automação, refeitas a cada `classificar` |

**A automação nunca escreve nas suas duas colunas.** Rodar `classificar` de novo recalcula os sinais
e preserva o que você decidiu, linha por linha.

`aplicar` lê a coluna `acao`, compara com o status que está no Parsifal e **só escreve o que está
diferente**. Rodar duas vezes seguidas não reescreve nada.

Rejeição exige critério, porque é o critério que registra em que etapa o estudo saiu. Aceite sem
critério usa o `criterio_de_aceite` da revisão.

## O que a automação faz e o que não faz

**Não exclui nada por conta própria.** Cada estudo sai com um de três rótulos:

| Rótulo | Significa |
|---|---|
| `MANTER` | nada a apontar: nenhum sinal disparou |
| `SINALIZAR` | tem algo a conferir, e a coluna `sinais` diz o quê |
| `SEM_RESUMO` | o registro chegou sem resumo: a ETAPA 1 não decide, segue para a 2 |

A decisão de excluir é sempre sua. O motivo é a assimetria de custo da ETAPA 1: **exclusão errada é
irrecuperável** (o estudo sai do funil e ninguém olha de novo), enquanto **inclusão errada custa uma
leitura na ETAPA 2**.

### Os campos lidos

**Título, palavras-chave e resumo.** As palavras-chave contam tanto quanto os outros dois: a busca
nas bases costuma rodar em `TITLE-ABS-KEY`, então um artigo pode ter entrado no corpus pelo
casamento na keyword. Ignorar essa coluna faria "termo ausente" medir a pobreza do export, e não o
artigo.

Pela mesma razão, **registro sem resumo não é decidido aqui**. Excluir por ausência de resumo seria
excluir pela lacuna do metadado.

### Os sinais

| Sinal | Dispara quando |
|---|---|
| Estudo secundário | aparece `survey`, `systematic review`, `mapping study`, `state of the art`... |
| Literatura cinza | título, resumo, keywords ou fonte tem `arXiv`, `preprint`, `technical report`, `thesis`... |
| Fora do domínio | aparece algum `termos_colisao` **e** nenhum `termos_dominio` |
| Fora do domínio | nenhum `termos_dominio` nem `siglas_ambiguas` nos três campos |
| Recorte ausente | nenhum `termos_recorte` nos três campos |

Os dois primeiros valem para qualquer tema e ficam no código. Os três últimos dependem do
vocabulário da revisão.

**Sigla ambígua não conta como prova de domínio.** No exemplo, `FL` é aprendizado federado, mas
também *fuzzy logic*. Um estudo cuja única marca do tema é a sigla, ao lado de `fuzzy` ou
`membership function`, é justamente o que precisa ser olhado. Com um termo inequívoco
(`federated learning`) no texto, a colisão é ignorada.

### As notas para a ETAPA 2

Idioma e contagem de páginas são calculados, mas **não entram na decisão da ETAPA 1**: os dois só
se confirmam com o arquivo aberto. Vão na coluna `notas_etapa_2` para poupar conferência depois.

O campo `language` do registro vence a detecção pelo texto: um artigo em russo com resumo em inglês
seria detectado como inglês. Quando o metadado não permite afirmar nada (campo de páginas vazio,
texto curto demais para detectar idioma), a automação fica calada em vez de encher a planilha de
ruído.

A coluna `recorte_em` diz *onde* o termo do recorte aparece: título, palavras-chave, ou resumo com
quantas menções. Não decide nada, serve para ordenar a ETAPA 2. Recorte no título é indício de foco;
uma menção solta no resumo é indício de menção.

## Como as decisões chegam no Parsifal

Quando você abre um artigo, escolhe o critério e salva, o navegador manda um POST para
`save_article_details/` com o formulário inteiro. A automação monta esse mesmo POST: abre o artigo,
lê os campos que já estão lá, troca **só** o status (`A` de aceito, `R` de rejeitado) e o critério,
e devolve o resto intacto. Por isso não usa navegador automatizado.

As rotas foram levantadas da instância hospedada (parsif.al v2.2.1), não do código do Parsifal no
GitHub, porque as duas divergem. Na hospedada os endpoints ficam sob `/reviews/conducting/`:
`source_articles/`, `article_details/`, `save_article_details/`.

Cuidados com os critérios cadastrados no Parsifal:

- **Um artigo carrega um critério só.** No modelo do Parsifal, o critério é chave estrangeira única,
  tanto no aceite quanto na rejeição.
- **Ao mexer num critério, edite o texto em vez de apagar e recriar.** O artigo aponta para o
  critério pelo id, e recriar quebraria marcação já feita.
- Os endpoints de ação em lote (`multiple_articles_action/`) só trocam o status e não gravam
  critério, então não são usados.

## Estrutura do repositório

```
config/revisoes.exemplo.json  modelo do config/revisoes.json, onde fica o vocabulário de cada revisão
triagem/regras.py             os sinais. É o coração, e é onde estão a maior parte dos testes
triagem/dados.py              lê dados/estudos.csv ou um .bib exportado das bases
triagem/parsifal.py           cliente HTTP: loga, lista artigos, lê a tela de cada um, marca no Parsifal
triagem/resumo_externo.py     busca o resumo na página do artigo quando o Parsifal não tem
triagem/planilha.py           escreve e lê o decisoes.xlsx
triagem/aplicacao.py          compara a planilha com o Parsifal e diz o que escrever
triagem/cli.py                os comandos
tests/                        pytest sobre as regras e sobre a leitura de HTML, sem rede
```

## Critério de sucesso

1. Uma pessoa tria ~50 estudos na ETAPA 1 à mão. Vira o conjunto de referência.
2. A automação roda sobre os mesmos 50: todo estudo excluído à mão tem que ter saído com
   `SINALIZAR` e o sinal correspondente. Sinal que não apareceu é buraco de regra.
3. `aplicar` sem `--confirmar` nunca escreve.
4. Rodar duas vezes seguidas não muda nada na segunda.

## O que já foi verificado ao vivo

Em 01/09/2026, contra uma revisão real na instância hospedada:

- login por usuário e senha
- `review-id` lido da página de estudos
- lista de artigos com id e status
- tela do artigo com resumo, palavras-chave, páginas, DOI e idioma
- os critérios de seleção com seus ids

**Não verificado: a escrita.** Ver o aviso na seção [Uso](#uso).
