# parsifal-auto

Ferramenta de linha de comando para a triagem de estudos de revisões sistemáticas feitas no
[Parsifal](https://parsif.al). Serve para qualquer tema: a regra da triagem é a própria string de
busca da revisão, colada num arquivo de configuração.

A ferramenta supõe uma seleção em três etapas, e os critérios cadastrados no Parsifal seguem esse
prefixo (`ETAPA 1 - ...`, `ETAPA 2 - ...`):

| Etapa | O que se lê | Quem decide | Critérios |
|---|---|---|---|
| ETAPA 1 | título, palavras-chave, resumo e o número de páginas do metadado | a string de busca e o mínimo de páginas, com conferência sua | os dois da string e, se a revisão quiser, o de short-paper |
| ETAPA 2 | introdução e resumo | você, à mão | todo critério de conteúdo: tema, tipo de estudo, preprint, idioma... |
| ETAPA 3 | texto completo | você, à mão | o que só se decide com o artigo inteiro aberto |

A ETAPA 1 tem só os critérios que se decidem sem julgamento, pelo registro:

```
ETAPA 1 - Atende à string de busca em título, resumo ou palavras-chave      (inclusão)
ETAPA 1 - Não atende à string de busca em título, resumo ou palavras-chave  (exclusão)
ETAPA 1 - Short-paper, com menos de 4 páginas                               (exclusão, opcional)
```

Qualquer outro critério pede leitura e julgamento (o estudo trata do tema? é secundário? é
preprint?) e por isso mora na ETAPA 2 ou 3, mesmo que se possa decidir lendo só o resumo. Assim cada
estudo excluído na ETAPA 1 saiu pela string ou pelo número de páginas, o que é fácil de descrever no
método. O texto e o limite do short-paper são seus: o exemplo usa 4 páginas.

A ferramenta só atua na ETAPA 1. Ela lê os estudos importados na revisão, verifica se cada um atende
à string de busca nos mesmos três campos em que a busca rodou nas bases, entrega uma planilha com a
decisão já preenchida e, depois da sua conferência, marca no Parsifal como aceito ou rejeitado, com o
critério anexado. É o mesmo que você faria abrindo artigo por artigo e clicando.

## Requisitos

- **Python 3.13.** É a versão em que o projeto foi desenvolvido e em que os testes passam.
- Uma conta no Parsifal com acesso à revisão a triar: dona da revisão ou colaboradora dela.
- Os estudos já importados na revisão (aba *Conducting > Import Studies* do Parsifal).
- Os critérios de ETAPA 1 cadastrados no Parsifal (*Planning > Selection Criteria*), com o
  texto exato que está no config, para a automação anexar às decisões dela. Cadastre **antes** de
  aplicar qualquer decisão: ver [Cuidados com os critérios](#cuidados-com-os-critérios).

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

Copie `config/revisoes.exemplo.json` para `config/revisoes.json` e cole nele a string da sua revisão.
Como o `.env`, o `revisoes.json` está no `.gitignore`: o repositório traz só o exemplo.

Cada revisão é um bloco identificado por uma sigla (`A`, `B`...). O exemplo usa um tema fictício,
aprendizado federado em dispositivos de borda:

```json
"A": {
  "nome": "Aprendizado federado em dispositivos de borda",
  "string": "(\"federated learning\" OR FedAvg) AND (\"edge device\" OR IoT)",
  "criterio_de_aceite": "ETAPA 1 - Atende à string de busca em título, resumo ou palavras-chave",
  "criterio_de_rejeicao": "ETAPA 1 - Não atende à string de busca em título, resumo ou palavras-chave",
  "minimo_de_paginas": 4,
  "criterio_de_short_paper": "ETAPA 1 - Short-paper, com menos de 4 páginas"
}
```

| Chave | O que é |
|---|---|
| `nome` | só para exibição |
| `string` | a string de busca, exatamente como foi colada nas bases. No JSON, as aspas internas levam `\` antes |
| `criterio_de_aceite` | critério anexado quando a automação aceita. Texto exato de um critério de inclusão cadastrado no Parsifal |
| `criterio_de_rejeicao` | critério anexado quando a automação rejeita por não atender à string. Texto exato de um critério de exclusão cadastrado no Parsifal |
| `minimo_de_paginas` | opcional. Estudo com menos páginas que isso, pelo metadado, sai como short-paper |
| `criterio_de_short_paper` | opcional, junto com o anterior. Critério de exclusão anexado ao short-paper |

`string`, `criterio_de_aceite` e `criterio_de_rejeicao` são obrigatórias. As duas de short-paper vêm
juntas ou não vêm: sem elas, o número de páginas não decide nada. Se um critério não estiver cadastrado no Parsifal, o
`classificar` avisa, e o `aplicar` recusa a linha em vez de gravar sem critério.

**A revisão é escolhida em dois lugares, e os dois precisam concordar:**

| Onde | O que decide | Usado por |
|---|---|---|
| `PARSIFAL_REVIEW_URL` no `.env` | com qual revisão do Parsifal a automação conversa | `verificar`, `baixar`, `completar`, `aplicar` |
| `--revisao` na linha de comando | qual bloco do `config/revisoes.json` vale | `classificar`, `aplicar` |

Se o `.env` aponta para a revisão B e o comando diz `--revisao A`, a automação baixa os estudos da
revisão B e aplica neles a string da A. Nada avisa: a planilha sai coerente e errada. O `--revisao`
tem `A` como padrão, então esquecê-lo também não dá erro.

## Uso

Com o ambiente ativado, da raiz do repositório:

```bash
python -m triagem verificar                # sonda a revisão, não escreve nada
python -m triagem baixar                   # copia os estudos para dados/estudos.csv
python -m triagem completar                # busca fora o resumo que o Parsifal não tem
python -m triagem classificar --revisao A  # gera dados/decisoes.xlsx com a decisão preenchida
#   abra a planilha, confira e mude o que discordar
python -m triagem aplicar --revisao A              # simulação: mostra o que seria escrito
python -m triagem aplicar --revisao A --confirmar  # grava no Parsifal
```

**Comece sempre por `verificar`** e confira se a primeira linha impressa (`revisão:`) é a URL que
você quer.

> **A escrita no Parsifal ainda não foi testada ao vivo.** Leitura e login foram verificados contra
> uma revisão real, mas nenhum `aplicar --confirmar` foi enviado até agora. Na primeira vez, deixe
> só **uma** linha com a coluna `acao` preenchida, rode `aplicar --confirmar` e confira na tela do
> Parsifal se o status e o critério entraram e se o resto do artigo (resumo, autores, DOI) continua
> intacto. Só depois aplique o resto.

Detalhes de cada comando:

- **`verificar`** mostra todos os critérios da revisão, mas guarda em `dados/criterios.json` só os de
  ETAPA 1, que são os únicos que a automação usa. As outras etapas ficam no Parsifal. Rode de novo ao
  trocar de revisão: o `classificar` confere os critérios do config contra esse arquivo.
- **`baixar`** faz uma requisição por artigo e demora. A instância hospedada do Parsifal não tem
  export: resumo e palavras-chave só existem na tela de cada artigo. Só os artigos ainda
  `Unclassified` são baixados. Queda de conexão ou erro passageiro do servidor é repetido até cinco
  vezes, com espera crescente. Use `--limite N` para testar com poucos e `--pausa` para ajustar o
  intervalo entre requisições (padrão 0,3 s).
- **`completar`** procura, pelo DOI ou pelo link, o resumo dos estudos que chegaram sem ele.
- **`classificar`** ignora estudo que já tem status no Parsifal, então rodar duas vezes não desfaz
  trabalho. Aceita `--entrada` para ler um `.csv` ou `.bib` no lugar de `dados/estudos.csv`.
- **`aplicar`** sem `--confirmar` nunca escreve.

Todos os comandos aceitam `--help`.

### Antes de trocar de revisão

A pasta `dados/` é uma só para todas as revisões: `baixar` sobrescreve o `estudos.csv`, e
`classificar` remonta o `decisoes.xlsx` só com os estudos da revisão nova. **Conferência feita na
planilha e ainda não aplicada some.** Rode `aplicar --confirmar` antes da troca, ou copie a pasta
(por exemplo, para `dados-A/`).

Para trocar: edite `PARSIFAL_REVIEW_URL` no `.env`, rode `verificar` e use a sigla certa no
`--revisao`.

## Como a ETAPA 1 é decidida

### A regra

Quando a revisão configura o short-paper, o número de páginas é olhado primeiro. Os demais estudos
são avaliados pela string de busca, sobre **título, resumo e palavras-chave juntos**. É o mesmo que o
`TITLE-ABS-KEY` do Scopus e o *Topic* do Web of Science fazem: cada termo pode estar em qualquer um
dos três campos.

| Situação | Decisão |
|---|---|
| menos páginas que o `minimo_de_paginas`, pelo metadado | `rejeitar`, com o `criterio_de_short_paper` |
| atende à string | `aceitar`, com o `criterio_de_aceite` |
| tem resumo e não atende à string | `rejeitar`, com o `criterio_de_rejeicao` |
| não tem resumo e não atende à string | conferência manual: a linha sai em branco |

**As páginas só decidem quando o número é confiável.** Elas são contadas pelo intervalo do campo
`pages` (`123-127` são 5 páginas). Intervalo de página única não conta: o IEEE exporta `1-1` para
artigo de periódico em *early access*, que ainda não tem paginação, e excluir esse artigo seria
excluir um trabalho completo. Campo vazio, número de artigo eletrônico (`e12345`) e formato estranho
também não contam. Nesses casos quem decide é a string, e o short-paper fica para a ETAPA 2, com o
arquivo aberto.

O caso sem resumo fica com você porque ali "não atende" mediria a lacuna do registro, e não o
artigo. Antes de chegar nele, o `completar` tenta buscar o resumo fora do Parsifal.

### A comparação

A comparação imita o que as bases fazem sozinhas, para que a triagem não seja mais rígida que a busca:

- **maiúscula e minúscula são iguais:** `LLM` casa com `llm`;
- **hífen e espaço são iguais:** `"on-device"` casa com *on device*, e `"full page"` com *full-page*;
- **plural regular conta:** `API` casa com *APIs*, e `"edge device"` com *edge devices*;
- **termo casa palavra inteira:** `API` não casa dentro de *rapid*;
- **frase entre aspas casa a sequência inteira**, e não atravessa de um campo para outro.

A string aceita termos soltos, frases entre aspas, `*` como curinga (`orchestrat*`), `AND`, `OR`,
`NOT` (também na forma `AND NOT`) e parênteses. `AND` tem precedência sobre `OR`, como nas bases.
Código de campo (`TITLE-ABS-KEY(...)`) e operador de proximidade (`NEAR/3`, `W/2`) são recusados
com erro, porque com eles a regra deixaria de ser a mesma da busca.

### A evidência

A coluna `evidencia` mostra, para cada grupo de sinônimos ligado por `AND` na string, os termos que
casaram, ou `nenhum termo` no grupo que faltou:

```
G1: LLM, LLMs | G2: nenhum termo | G3: mobile
```

É ela que permite conferir uma rejeição sem abrir o artigo, e descrever no método por que cada
estudo saiu.

### Limites conhecidos

- **Lematização.** As bases também casam formas que não são plural regular (*strategy* e
  *strategies*, por exemplo). Aqui só o plural com `s` e `es` é coberto. Um termo com plural
  irregular precisa estar na string nas duas formas, ou com curinga.
- **Palavras-chave indexadas.** Algumas bases casam a busca também no vocabulário controlado delas,
  que nem sempre vem no export. Um estudo que entrou só por esse caminho sai aqui como `rejeitar`.
  Por isso a planilha é conferida antes do `aplicar`: vale olhar uma amostra das rejeições.

## As notas para a ETAPA 2

O idioma é calculado, mas **não entra na decisão da ETAPA 1**: ele só se confirma com o arquivo
aberto. Vai na coluna `notas_etapa_2` para poupar conferência depois.

O campo `language` do registro vence a detecção pelo texto: um artigo em russo com resumo em inglês
seria detectado como inglês. Sem o campo, a detecção roda sobre título e resumo e só vira nota quando
afirma outro idioma com confiança alta. Texto curto demais não vira nota, em vez de encher a planilha
de ruído.

## A planilha de trabalho

`dados/decisoes.xlsx`. É XLSX e não CSV porque traz filtro e busca por coluna, que é o que falta na
tela do Parsifal.

| Coluna | O que é |
|---|---|
| **`acao`** | `aceitar` ou `rejeitar`, preenchida pela automação. Mude o que discordar. Vazio quer dizer "não aplicar" |
| **`criterio`** | o critério que vai junto, também preenchido. A aba `criterios` da planilha tem os critérios de ETAPA 1 lidos do Parsifal |
| `automacao` | a decisão original da automação (`aceitar`, `rejeitar`, `short-paper` ou `manual`), para comparar com a sua |
| `evidencia` | os termos da string que casaram, grupo por grupo, e o número de páginas no caso de short-paper |
| `notas_etapa_2` | idioma |

**O que você muda é seu.** Rodar `classificar` de novo recalcula só as linhas em que `acao` e
`criterio` continuam como a automação preencheu. Linha em que você mudou qualquer uma das duas fica
como está.

`aplicar` lê a coluna `acao`, compara com o status que está no Parsifal e **só escreve o que está
diferente**. Rodar duas vezes seguidas não reescreve nada. Rejeição sem critério é recusada, porque é
o critério que registra em que etapa o estudo saiu.

## Como as decisões chegam no Parsifal

Quando você abre um artigo, escolhe o critério e salva, o navegador manda um POST para
`save_article_details/` com o formulário inteiro. A automação monta esse mesmo POST: abre o artigo,
lê os campos que já estão lá, troca **só** o status (`A` de aceito, `R` de rejeitado) e o critério,
e devolve o resto intacto. Por isso não usa navegador automatizado. O POST nunca é repetido
automaticamente: repetir sem saber se o primeiro chegou seria escrever às cegas.

As rotas foram levantadas da instância hospedada (parsif.al v2.2.1), não do código do Parsifal no
GitHub, porque as duas divergem. Na hospedada os endpoints ficam sob `/reviews/conducting/`:
`source_articles/`, `article_details/`, `save_article_details/`.

Os endpoints de ação em lote (`multiple_articles_action/`) só trocam o status e não gravam critério,
então não são usados.

### Cuidados com os critérios

- **Um artigo carrega um critério só.** No modelo do Parsifal, o critério é chave estrangeira única,
  tanto no aceite quanto na rejeição.
- **O Parsifal não edita critério: só adiciona e remove.** Para mudar o texto ou a etapa de um
  critério, adicione o novo e depois remova o antigo.
- **Remover um critério apaga o critério dos artigos que já o usavam.** O artigo continua aceito ou
  rejeitado, mas sem dizer por quê. Por isso a lista de critérios se acerta **antes** do primeiro
  `aplicar`. Depois disso, mexer num critério em uso significa remarcar os artigos dele.

## Estrutura do repositório

```
config/revisoes.exemplo.json  modelo do config/revisoes.json: a string e os dois critérios de cada revisão
triagem/string_de_busca.py    lê a string e avalia cada estudo. É o coração da triagem
triagem/regras.py             a decisão da ETAPA 1 e as notas de idioma e páginas
triagem/dados.py              lê dados/estudos.csv ou um .bib exportado das bases
triagem/parsifal.py           cliente HTTP: loga, lista artigos, lê a tela de cada um, marca no Parsifal
triagem/resumo_externo.py     busca o resumo na página do artigo quando o Parsifal não tem
triagem/planilha.py           escreve e lê o decisoes.xlsx
triagem/aplicacao.py          compara a planilha com o Parsifal e diz o que escrever
triagem/cli.py                os comandos
tests/                        pytest sobre a string, as regras e a leitura de HTML, sem rede
```

## Critério de sucesso

1. Uma pessoa tria ~50 estudos na ETAPA 1 à mão. Vira o conjunto de referência.
2. A automação roda sobre os mesmos 50 e a concordância é medida: cada divergência é lida para saber
   se a causa é a string, o registro (resumo ou palavras-chave faltando) ou a comparação.
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
