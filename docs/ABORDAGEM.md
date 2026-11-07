# Reconstrução do mirror Accrue → site da Alinia

Este documento aplica o método da nota **ABORDAGEM** (pipeline de 9 etapas usado no mirror `good-fella`) ao pacote `references/accrue_framer_ai_page-mirror-v1.6.0.zip`. Aqui ficam o que mudou no método por se tratar de um site **Framer** (e não Next.js/Turbopack), as decisões de tradução e as divergências conscientes.

Os princípios continuam os mesmos:

1. **Número só entra se vier do código.** Tempos, curvas, offsets e cores foram lidos dos módulos ou do CSS. Quando houve adaptação, ela está na seção 5.
2. **Uma fonte de verdade por camada.** CSS diz *como parece*, JS diz *como se move*, HTML diz *com quais dados*.
3. **Validar no navegador.** Nada foi dado como pronto sem screenshot e roteiro de interação.

---

## 1. Pipeline aplicado

| Etapa da nota | Como ficou no Framer |
|---|---|
| (1) Triagem | 569 KB de HTML, 72 JS, 8 CSS, 76 imagens, 7 fontes. Fingerprint: `import … from "framerusercontent.com/…/rolldown-runtime.mjs"` → **Framer com rolldown (ESM)**. Scripts `data-pm-generated` do Page Mirror ignorados. |
| (2) REA | `analyze_javascript_application` (MCP) no diretório `assets/js`: **72 arquivos, 0 falhas de parse, ~1,66 M nós de AST**, evidência `ev_1e103d90…6370`. Cobertura semântica **parcial** (orçamento de resultado estourado de `script-015` em diante). Mesmo uso da nota: integridade e inventário, não reconstrução. |
| (3) Dados serializados | Não há RSC. O equivalente no Framer: **HTML SSR completo** (texto e árvore com `data-framer-name`) + `<script type="framer/appear">` (`__framer__appearAnimationsContent` e `__framer__breakpoints`). |
| (4) Separar módulos | Desnecessário: rolldown já entrega um módulo ESM por chunk. Bastou `prettier --parser babel` nos arquivos relevantes. |
| (5) Leitura dirigida | O índice veio de `X.displayName = \`Nome\`` em cada chunk (ver tabela abaixo). Cada componente Framer **embute o próprio CSS** num array de strings logo antes do `displayName`. |
| (6) CSS | Tokens `--token-<uuid>` (14 cores) e presets `.framer-styles-preset-*` tabulados por uso no HTML. Layout lido das classes `.framer-<hash>` (container 1300px, gutter 32px, hero `padding-top: 196px`). |
| (7) Assets | Logos de clientes, fotos e ícones 3D **não foram copiados** (ver seção 5). Fontes: Geist Mono e Inter (OFL) via Google Fonts; Helvetica Neue (licenciada) substituída. |
| (8) Tradução | React/framer-motion → HTML estático + ES modules + CSS. Detalhes na seção 3. |
| (9) Validação | puppeteer-core + Chrome (SwiftShader): screenshots por seção em 1440px e 390px, roteiro de interação, console limpo. |

### Índice de componentes (displayName → chunk)

| Chunk | Componentes usados na Home |
|---|---|
| `script-006` | Lenis, Navbar, Nav Link, Button Primary, **Liquid Metal**, Text Shimmer, spotlight do rodapé |
| `script-008` | Section Label (badge) |
| `script-012` | **Home**, Animated Pattern Background, MCP & Dev Card, Animated Chart Line, Copy Clipboard, Security Card, **Tab Items** (casos de uso), Stats Card 2, Ruler Scale |
| `script-015` | FAQ, Animated Number Counter, Testimonial Card/Tab |
| `script-017` | **AI Chat Card**, Live Overview Card, Automation Flow Card, Integrations Flow Card, Rotating Integrations, **Fluted Swirl** |
| `script-018` | Brand Section (faixa de logos) |
| `script-044` | Liquid Metal Border, Stats Card 1 |

---

## 2. Números extraídos

| Componente | Valores do bundle |
|---|---|
| Lenis | `duration: intensity / 10`, `intensity: 6` → **0.6** |
| Entrada do hero | opacity `.001 → 1`, spring `{bounce: 0, duration: .6, delay: .2}` |
| Button Primary | padding externo 2px, raio 6/4, face `8px 21px`; metal 180px de altura, `left/right: -7px`; texto duplicado que sobe 18px no hover (spring .6) |
| Section Label | padding 2px, canvas com `inset: -20px`, conteúdo `4px 8px 4px 4px` com gradiente `#fcfcfe → #f2f2f2` |
| Liquid Metal | `repetition 2, shiftRed/Blue .3, contour .4`; badge `speed 1.4, distortion .01`; botão `speed 1, distortion .07`; fase = `((t·speed/1000/16) % 1)·2π` |
| Fluted Swirl | preset `Bs`: paleta `#C4BFB7 #A6591E #8F8F8F #9BAACF #3C5385`, `frequency 10`, `angle 31`, `aberration .414`, `glassSpeed .15`, cena em ½ resolução, buffer ≤ 4,2 MP |
| AI Chat Card | 1 Typing **2000** → 2a Sent **850** → 2 Thinking **1200** → 3 Answered **800** → 3b **800** → 4a **1200** → 4 Follow-up; transição 450ms `[.42,0,.58,1]` |
| Tab Items | 5 abas (20%), 303 traços (101 por largura), faixa `K = G·(0.1 + i/5)`, `900ms cubic-bezier(.22,1,.36,1)`; texto 320/220ms com `blur(4px)`, corpo +40ms; grid `.85fr/1.15fr`, gap 56, mídia 504px |
| Animated Number Counter | estatísticas: delay .4s, 1.4s, `[.44,0,.56,1]`; card: spring 1s |
| FAQ | 0.3s `[.44,0,.56,1]` |
| Animated Pattern Background | binário, padrão "3", `freqA 10, freqB 20, speedA 30, speedB 35, scale 1.1`, 12px, `rgba(255,255,255,.24)`, a cada 0,2s |
| Spotlight | raio 180px, gradiente `#66ccff → #fff → #66ccff` a 90°, base 15% branco, varredura 5s + 0,4s |

---

## 3. Tradução Framer → HTML/CSS/JS

| No original | Na reconstrução | Por quê |
|---|---|---|
| Variantes de componente (`cycleOrder`, `activeVariantCallback`, `delay(…, ms)`) | `async` + `await sleep(ms)` em sequência (`chat-sequence.js`, `flow-card.js`) | A máquina de variantes vira um roteiro linear legível |
| framer-motion `transition: {type: spring, bounce: 0, duration: .6}` | `cubic-bezier(.25,1,.5,1)` 600ms (`--ease-spring`) | Mola criticamente amortecida ≈ ease-out; sem dependência |
| Arrays `ease: [x1,y1,x2,y2]` | `bezier()` em `lib/easing.js` e variáveis `--ease-*` | Os números do bundle entram sem conversão manual |
| `useInView` | `observeVisibility` / `whenVisible` (`lib/dom.js`) | Mesmo gatilho |
| Um WebGL por instância do Liquid Metal | **um renderer compartilhado** que desenha em cada `<canvas>` 2D | ~15 instâncias estouram o limite de contextos do navegador |
| Relógio `J` (elapsed/last/subscribers) | `lib/ticker.js` | Um rAF para a página toda, pausa com aba oculta |
| Tab Items em React com estilos inline | HTML semântico (`role="tablist"`) + CSS + 60 linhas de JS | Mesma geometria da régua, teclado preservado |
| Mask CSS sobre SVG do logo (spotlight) | `<mask>` SVG com `<circle>` que segue o ponteiro | Funciona com texto, sem imagem |

### Ordem de boot (`main.js`)

1. `html.js` (o CSS só esconde `[data-appear]` com JS ativo).
2. `document.fonts.ready` — régua, carrossel de regras e padrão ASCII medem texto.
3. Lenis antes do header (o menu mobile para/retoma o scroll).
4. Componentes de cima para baixo, cada um isolado por `safely()`.
5. Entrada do hero.

---

## 4. Conteúdo

O texto do template (fintech fictícia "Accrue") foi substituído pelo produto do `produto.md` (PRD v4.1 — Workforce Intelligence). Os números exibidos vêm do exemplo revisado da **Unidade Centro** (seção 10 do PRD): demanda 1.150 → 1.200, capacidade ~999,8 / ~954 / ~908,9 por jornada, IPD 1,15 / 1,21 / 1,27, gaps 3 / 3 / 4.

| Seção do template | Na Alinia |
|---|---|
| Logos de clientes | Fontes de dados suportadas (CSV, Jira, Linear, WFM, Ponto, ERP) |
| Capabilities (4 cards) | Investigação · Previsão · Cenários · Regras de jornada |
| Use cases (setores) | Personas: RH, Operações, Jurídico, Financeiro, Liderança |
| Customer stories | **Exemplo Unidade Centro** (mesma interação; nenhum depoimento inventado) |
| Built to scale (métricas de uso) | Garantias de design do PRD (5 cenários, 4 agentes, 100% aprovação humana, 0 desligamentos) |
| MCP & API | **Auditoria**: `DecisionRecord` verificável |
| Changelog com datas | Mudanças da revisão v4.0 → v4.1 |

---

## 5. Divergências conscientes

| Item | Original | Reconstrução | Motivo |
|---|---|---|---|
| Fonte de títulos | Helvetica Neue | Inter (mesmo tracking/line-height) | licença |
| Logos, fotos, ícones 3D, screenshot do dashboard | imagens do template | painel do app em HTML, fotos editoriais e superfícies abstratas originais da Alinia, ícones SVG próprios | não redistribuir assets de um template pago |
| Campo de "tinta" do Fluted Swirl | simulação 128×128 na CPU seguindo o cursor | não portado (`uFieldOn = 0`) | custo/benefício; o resto do shader é idêntico |
| Máscara do Liquid Metal | SVG → textura SDF | SDF analítico do retângulo | só a variante `source: none` é usada |
| CTA do rodapé | imagem estática | mesmo Fluted Swirl com preset escuro | coerência visual sem asset externo |
| Cards de Previsão/Fluxo/Regras | timelines específicas do Framer | sequências próprias com as mesmas curvas/durações base | tempos exatos desses três não foram extraídos um a um |
| Spring do framer-motion | física de mola | `cubic-bezier(.25,1,.5,1)` | sem dependência de runtime |

---

## 6. Validação

- **Desktop 1440px:** 14 screenshots por seção; console sem erros.
- **Roteiro de interação:** hover no botão, aba "Jurídico trabalhista" (régua em `618px` = `1236 × (0,1 + 2/5)`), card "Jornada 40h", FAQ exclusivo, copiar comando (clipboard conferido), sequência completa do chat, header escuro sobre seção escura.
- **Mobile 390px:** sem overflow horizontal (`scrollWidth = 390`), menu abre e fecha.

**Não validado:** Safari/Firefox, `prefers-reduced-motion` no navegador real, leitores de tela além da semântica básica.

## 7. Próximos passos

1. Ligar os CTAs (`#contato`) ao canal real de agendamento.
2. Portar o campo de tinta do Fluted Swirl, se a interação com o cursor for desejada.
3. Refinar o enquadramento das fotos próprias nos casos de uso após revisão visual em outros navegadores.
4. Testar em Safari (WebGL2 + `SRGB8_ALPHA8`) e Firefox.
