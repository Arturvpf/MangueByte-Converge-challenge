# Site da Alinia

Landing page e protótipo navegável da plataforma **Alinia — Workforce Intelligence**. A estrutura e os comportamentos da landing foram reconstruídos a partir do mirror do template Framer "Accrue" (`../references`), seguindo o método da nota ABORDAGEM; o conteúdo vem do PRD (`../produto.md`). Detalhes do processo em [`docs/ABORDAGEM.md`](docs/ABORDAGEM.md).

HTML + CSS + ES modules nativos. Sem framework e sem dependências de build; a única biblioteca é o Lenis, vendorizado em `src/scripts/vendor/`.

## Comandos

```bash
npm run dev       # serve src/ em http://localhost:5173
npm run build     # copia src/ -> dist/ (diretório publicado, ver .openai/hosting.json)
npm run preview   # build + serve dist/ em http://localhost:4173
```

O site precisa ser servido via HTTP: ES modules e WebGL não funcionam em `file://`.

## Protótipo da plataforma

Abra `/app/` no mesmo servidor. A landing também oferece o link **Explorar plataforma**. O protótipo reúne cinco telas: visão geral, investigação, previsão, cenários e revisão do RH. Há navegação por hash, detalhe de evidências, alternância de faixas de demanda, comparação de até dois cenários e preparação local de um checklist.

Os números vêm do exemplo ilustrativo da Unidade Centro no PRD ou são séries demonstrativas identificadas na interface. Não há backend, dados reais, persistência, integração, aprovação administrativa ou requisição de vaga.

## Estrutura

```
src/
├── index.html                 # toda a página, seção por seção
├── assets/icons/favicon.svg
├── assets/images/             # quatro imagens originais geradas para a Alinia
├── styles/
│   ├── main.css               # só @imports, na ordem de cascata
│   ├── tokens.css             # cores, tipografia, espaço, curvas (lidos do CSS do Framer)
│   ├── base.css               # reset, tipografia global, utilitários
│   ├── layout.css             # container, trilhos, divisores, cabeçalho de seção
│   ├── components/            # badge, button, header, widget, motion
│   └── sections/              # hero, process, capabilities, use-cases, example,
│                              # scale, security, changelog-faq, footer
└── scripts/
    ├── main.js                # boot: fontes -> Lenis -> componentes
    ├── lib/                   # dom, ticker (rAF único), easing (bezier/tween), webgl
    ├── components/            # um arquivo por comportamento (ver abaixo)
    └── vendor/lenis.mjs
scripts/build.mjs, scripts/serve.mjs   # Node puro, sem dependências
docs/ABORDAGEM.md                       # método, números extraídos, divergências
```

## Componentes

| Arquivo | Origem no Framer | Ativado por |
|---|---|---|
| `fluted-swirl.js` | Fluted Swirl (shader WebGL2 do hero) | `canvas[data-fluted-swirl]` (`="dark"` no rodapé) |
| `liquid-metal.js` | Liquid Metal (moldura de badges/botões) | `[data-metal]`, `[data-metal="badge"]` |
| `smooth-scroll.js` | Lenis (`duration 0.6`) | automático |
| `header.js` | Navbar Light/Dark + menu mobile | `[data-header]`, `[data-menu-toggle]` |
| `capabilities-nav.js` | Single Tab + barra lateral | `[data-capabilities]` |
| `chat-sequence.js` | AI Chat Card | `[data-chat]` |
| `live-overview.js` | Live Overview Card | `[data-overview]`, `[data-dot-row]` |
| `flow-card.js` | Automation Flow Card | `[data-flow]` |
| `rule-carousel.js` | Rotating Integrations | `[data-rules]` |
| `ruler-tabs.js` | Tab Items (régua) | `[data-ruler-tabs]` |
| `typewriter.js` | Process Card 2 | `[data-typewriter]` |
| `expand-cards.js` | Testimonial Tab | `[data-expand-cards]` |
| `counter.js` | Animated Number Counter | `[data-counter]` |
| `area-chart.js` | Animated Chart Line | `[data-chart]` |
| `ascii-pattern.js` | Animated Pattern Background | `canvas[data-ascii-pattern]` |
| `copy-button.js` | Copy Clipboard | `[data-copy]` |
| `accordion.js` | FAQ | `[data-accordion]` |
| `spotlight.js` | spotlight do wordmark | `[data-spotlight]` |

Todos respeitam `prefers-reduced-motion` (estado final estático) e só animam quando visíveis.

## Pendências

- Os CTAs apontam para `#contato`; trocar pelo link real de agendamento.
- Testado em Chrome (desktop 1440px e mobile 390px). Falta Safari e Firefox.
