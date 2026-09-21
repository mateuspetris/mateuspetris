# assets/

SVGs usados pelo `README.md` do perfil. Todos são autocontidos: sem scripts, sem
fontes web, sem imagens externas, sem servidor. Funcionam dentro de `<img>` no GitHub.

| Arquivo | O que é | Animado? |
|---|---|---|
| `hero-observatory.svg` | Peça central: esfera, órbitas, nome, cargo | Sim (SMIL, bem lento) |
| `section-about.svg`, `section-missions.svg`, `section-transmission.svg` | Cabeçalhos de seção (régua graduada) | Não |
| `mission-search-sort.svg` | Glifo do Search & Sort Laboratory | Só a faixa de comparação |
| `mission-lru-cache.svg` | Glifo do LRU Cache | Não |

## Como editar

**Não edite os SVGs à mão.** O hero contém centenas de valores calculados (a esfera
é uma projeção 3D real). Edite `tools/build_assets.py`, no bloco `CONFIG` do topo, e rode:

```bash
python3 tools/build_assets.py
```

Precisa apenas do Python 3 (nenhuma dependência). Depois faça commit dos SVGs gerados.

| Quero mudar… | Onde |
|---|---|
| Nome e cargos | `NAME`, `TITLE`, `TITLE_2` |
| Frases que se alternam sob o nome | `TICKER` (e `TICKER_SECONDS_EACH`) |
| Tecnologias em órbita | `ORBIT_LABELS` (texto, anel, ângulo, legenda, haste) |
| Cores | `PALETTE` |
| Formato dos anéis | `ORBITS` (raios, inclinação, cor, tracejado) |
| Satélites que percorrem os anéis | `SATELLITES` |
| Velocidade de rotação da esfera | `SPIN` (graus por segundo; padrão 1) |
| Títulos das réguas de seção | `SECTIONS` |

## Estrutura do hero (ids dos grupos no SVG)

Da camada mais ao fundo para a mais à frente:

1. `nebula`, `stars`, `webb-stars`, `chart-frame`: fundo e moldura de carta celeste
2. `orbits-back`: metade de trás dos anéis (passa **atrás** da esfera)
3. `globe`: esfera (corpo, paralelos, meridianos que giram, grafo de nós, luz de borda)
4. `orbits-front`: metade da frente dos anéis (passa **sobre** a esfera)
5. `orbit-labels`: tecnologias com haste
6. Textos: estação, nome, cargo, frases alternadas

## Por que é assim (limitações do GitHub)

- **Fontes:** o GitHub bloqueia fontes web dentro de SVG, então o texto usa pilhas de
  fontes do sistema (`Inter`, `SF Pro`, `Segoe UI`, `Helvetica Neue`, `Arial` e, para
  os rótulos, fontes monoespaçadas). A aparência varia um pouco entre sistemas.
- **Animação:** feita com SMIL (`<animate>`), que roda em `<img>`. JavaScript não roda.
  Todo o movimento é lento (a esfera leva 6 minutos por volta).
- **Tema claro/escuro:** o hero é um painel escuro nos dois temas. Os cabeçalhos de
  seção usam uma placa escura + régua cinza para manterem contraste em ambos.

## QA local

Para ver um quadro estático em um instante qualquer (o script escreve em `assets/_preview/`):

```bash
python3 tools/build_assets.py --freeze 90
```

Você pode apagar `_preview/` quando quiser.
