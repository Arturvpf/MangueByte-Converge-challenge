/**
 * Liquid Metal — moldura metálica animada de badges e botões.
 *
 * Port do componente "Liquid Metal" (script-006/044/008). O GLSL é o do
 * bundle; a diferença é estrutural: o original cria um contexto WebGL por
 * instância. Como a página tem ~15 instâncias e o navegador derruba
 * contextos acima de ~16, aqui existe UM renderer WebGL2 compartilhado que
 * desenha cada instância e copia o resultado para o <canvas> 2D dela.
 *
 * Uso no HTML: `data-metal` em .btn ou `data-metal="badge"` em .badge.
 * O JS injeta o <canvas class="metal"> como primeiro filho.
 */

import { onTick } from '../lib/ticker.js';
import { createProgram } from '../lib/webgl.js';
import { observeVisibility, prefersReducedMotion, qsa } from '../lib/dom.js';

/* Constantes fixas do shader no original (objeto `q`). */
const FIXED = {
  colorTint: [1, 1, 1],
  repetition: 2,
  shiftRed: 0.3,
  shiftBlue: 0.3,
  contour: 0.4,
};

/* Props por instância lidas das páginas. */
export const METAL_PRESETS = {
  badge: { angle: 70, distortion: 0.01, softness: 0.1, speed: 1.4, scale: 1 }, // Section Label
  button: { angle: 70, distortion: 0.07, softness: 0.1, speed: 1, scale: 1 }, // Button Primary
};

/* Fase: ciclo de 16s -> 0..2π  ((elapsed * speed / 1000 / 16) % 1) * TAU */
const CYCLE_SECONDS = 16;

const VERTEX = `#version 300 es
layout(location = 0) in vec2 aPosition;
out vec2 vUv;
void main() {
  vUv = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;

const FRAGMENT = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 fragColor;

uniform vec2  uResolution;
uniform vec3  uColorTint;
uniform float uRepetition;
uniform float uSoftness;
uniform float uShiftRed;
uniform float uShiftBlue;
uniform float uDistortion;
uniform float uContour;
uniform float uAngle;
uniform float uPhase;
uniform float uScale;

const vec3 METAL_DARK  = vec3(20.0, 20.0, 22.0) / 255.0;
const vec3 METAL_COOL  = vec3(64.0, 67.0, 80.0) / 255.0;
const vec3 METAL_LIGHT = vec3(250.0, 250.0, 255.0) / 255.0;
const float COOL_PIVOT = 0.14;

const float BAND_DARK_END  = 0.045;
const float BAND_LIGHT_END = 0.17;
const float RAMP_LIFT      = 0.78;

const float FIELD_GAIN      = 1.00;
const float BREATH_GAIN     = 0.56;
const float DISTORTION_GAIN = 0.45;
const float CONTOUR_GAIN    = 0.55;
const float CONTOUR_FALLOFF = 3.0;
const float RIM_GAIN        = 0.38;
const float RIM_FALLOFF     = 18.0;
const float RIM_REFRACTION  = 1.8;

const float DISP_PHASE      = 0.012;
const float DISP_WORLD      = 0.020;
const float GREEN_BIAS      = 0.05;
const float CHROMA_STRENGTH = 0.95;
const float PLATEAU_FALLOFF = 16.0;
const float BLOOM_MIN       = 0.55;
const float BLOOM_MAX       = 1.80;

const float CUSP_SCALE = 0.25;
const float CUSP_ROUND = 0.34;
const float SOFT_MIN   = 0.0035;
const float SOFT_MAX   = 0.2000;

vec3 metalRamp(vec3 t) {
  vec3 k1 = clamp(t / COOL_PIVOT, 0.0, 1.0);
  vec3 k2 = clamp((t - COOL_PIVOT) / (1.0 - COOL_PIVOT), 0.0, 1.0);
  return mix(mix(METAL_DARK, METAL_COOL, k1), METAL_LIGHT, k2);
}

mat2 rot(float a) {
  float c = cos(a);
  float s = sin(a);
  return mat2(c, -s, s, c);
}

float sdRoundedBox(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

float hash21(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}

float valueNoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y) * 2.0 - 1.0;
}

float liquidField(vec2 q, float ph) {
  vec2 w = q + 0.20 * vec2(sin(q.y * 0.85 + ph), cos(q.x * 0.78 - ph));
  float f = 0.42 * sin(w.y * 1.55 + 1.9);
  f += 0.34 * sin(w.x * 1.35 + 0.6);
  f += 0.24 * sin((w.x + w.y) * 1.30);
  f += BREATH_GAIN * sin(ph);
  return f;
}

float stripeTone(float phase, float e) {
  float u = fract(phase);
  float light = smoothstep(BAND_DARK_END - e, BAND_DARK_END + e, u)
              - smoothstep(BAND_LIGHT_END - e, BAND_LIGHT_END + e, u);
  float ramp = pow(smoothstep(BAND_LIGHT_END + e, 1.0 - e, u), RAMP_LIFT)
             * (1.0 - smoothstep(1.0 - e, 1.0, u));
  return clamp(light + ramp, 0.0, 1.0);
}

vec3 colorBurn(vec3 base, vec3 blend) {
  return 1.0 - min(vec3(1.0), (1.0 - base) / max(blend, vec3(1.0 / 255.0)));
}

void main() {
  // Sem máscara (source: none): o "mundo" é o retângulo do canvas.
  vec2 fragPx = vUv * uResolution;
  float fitDim = min(uResolution.x, uResolution.y);
  float pxPerWorld = fitDim * uScale * 0.5;
  vec2 p = (fragPx - 0.5 * uResolution) / max(pxPerWorld, 1.0);
  vec2 canvasHalf = uResolution / max(fitDim, 1.0);
  float sd = sdRoundedBox(p, canvasHalf / max(uScale, 0.0001), 0.0);

  vec2 pa = rot(-uAngle) * p;
  float f = liquidField(pa, uPhase);

  if (uDistortion > 0.0) {
    vec2 drift = 0.55 * vec2(cos(uPhase), sin(uPhase));
    float n = valueNoise(pa * 1.45 + drift) * 0.75 + valueNoise(pa * 2.90 - drift * 1.70) * 0.25;
    f += uDistortion * DISTORTION_GAIN * n;
  }

  float depth = max(-sd, 0.0);
  float rim = exp(-depth * RIM_FALLOFF);
  if (uContour > 0.0) {
    f += uContour * (CONTOUR_GAIN * exp(-depth * CONTOUR_FALLOFF) + RIM_GAIN * rim);
  }

  float phase = f * uRepetition * FIELD_GAIN;
  vec2 dPhase = vec2(dFdx(phase), dFdy(phase));
  float phasePerPixel = length(dPhase);
  float phasePerWorld = phasePerPixel * pxPerWorld;

  float e = max(SOFT_MIN + SOFT_MAX * uSoftness * uSoftness, phasePerPixel * 0.80);
  float calm = CUSP_SCALE / (CUSP_SCALE + phasePerWorld);
  e = min(e + CUSP_ROUND * calm * calm * calm, 0.14);

  vec2 gradDir = dPhase / max(phasePerPixel, 1.0e-6);
  float axial = abs(gradDir.x * 0.80 + gradDir.y * 0.60);
  float bloom = mix(BLOOM_MIN, BLOOM_MAX, axial);
  float disperse = (DISP_PHASE + phasePerWorld * DISP_WORLD) * bloom
                 * (1.0 + RIM_REFRACTION * rim * uContour) * (1.0 + e * 2.0);
  float dR = disperse * uShiftRed;
  float dB = disperse * uShiftBlue;

  float lum = stripeTone(phase, e);
  vec3 tone = vec3(
    stripeTone(phase - dR, e),
    stripeTone(phase - dR * GREEN_BIAS, e),
    stripeTone(phase + dB, e));
  float activity = 1.0 - pow(abs(2.0 * lum - 1.0), PLATEAU_FALLOFF);
  tone = mix(vec3(lum), tone, CHROMA_STRENGTH * activity);

  vec3 metal = colorBurn(metalRamp(tone), uColorTint);
  fragColor = vec4(metal, 1.0);
}`;

/* --- Renderer compartilhado ----------------------------------------------- */

class SharedMetalRenderer {
  constructor() {
    this.canvas = document.createElement('canvas');
    const gl = this.canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      preserveDrawingBuffer: true,
    });
    if (!gl) throw new Error('WebGL2 indisponível');
    this.gl = gl;
    const { program, uniforms } = createProgram(gl, VERTEX, FRAGMENT);
    this.uniforms = uniforms;

    gl.useProgram(program);
    gl.bindVertexArray(gl.createVertexArray());
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    gl.uniform3fv(uniforms.uColorTint, FIXED.colorTint);
    gl.uniform1f(uniforms.uRepetition, FIXED.repetition);
    gl.uniform1f(uniforms.uShiftRed, FIXED.shiftRed);
    gl.uniform1f(uniforms.uShiftBlue, FIXED.shiftBlue);
    gl.uniform1f(uniforms.uContour, FIXED.contour);
  }

  /** Garante que o canvas compartilhado comporte w x h (só cresce). */
  ensureSize(w, h) {
    if (this.canvas.width < w) this.canvas.width = Math.ceil(w);
    if (this.canvas.height < h) this.canvas.height = Math.ceil(h);
  }

  /** Desenha uma instância no canto superior esquerdo e devolve a área. */
  render(w, h, params, phase) {
    const { gl, uniforms } = this;
    this.ensureSize(w, h);
    // origem do GL é embaixo; posiciona o viewport no topo para o drawImage
    gl.viewport(0, this.canvas.height - h, w, h);
    gl.uniform2f(uniforms.uResolution, w, h);
    gl.uniform1f(uniforms.uSoftness, Math.min(1, Math.max(0, params.softness)));
    gl.uniform1f(uniforms.uDistortion, Math.max(0, params.distortion));
    gl.uniform1f(uniforms.uAngle, (params.angle * Math.PI) / 180);
    gl.uniform1f(uniforms.uScale, params.scale);
    gl.uniform1f(uniforms.uPhase, phase);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}

let shared = null;
function getRenderer() {
  if (shared === null) {
    try {
      shared = new SharedMetalRenderer();
    } catch (error) {
      console.warn('[liquid-metal]', error.message);
      shared = false; // fica no gradiente CSS de fallback
    }
  }
  return shared || null;
}

/* --- Instâncias ------------------------------------------------------------- */

const visible = new Set();
let stopTicking = null;

function drawInstance(instance, elapsed) {
  const renderer = getRenderer();
  if (!renderer) return;
  const { canvas, ctx, params } = instance;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
  const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const phase = (((elapsed * params.speed) / 1000 / CYCLE_SECONDS) % 1) * Math.PI * 2;
  renderer.render(w, h, params, phase);
  ctx.drawImage(renderer.canvas, 0, 0, w, h, 0, 0, w, h);
  canvas.style.background = 'none';
}

function syncTicker() {
  if (visible.size > 0 && !stopTicking && !prefersReducedMotion()) {
    stopTicking = onTick((elapsed) => {
      for (const instance of visible) drawInstance(instance, elapsed);
    });
  } else if (visible.size === 0 && stopTicking) {
    stopTicking();
    stopTicking = null;
  }
}

/** Cria a moldura metálica dentro de `host` (.btn ou .badge). */
export function createLiquidMetal(host, preset) {
  const canvas = document.createElement('canvas');
  canvas.className = 'metal';
  canvas.setAttribute('aria-hidden', 'true');
  host.prepend(canvas);

  const instance = { canvas, ctx: canvas.getContext('2d'), params: { ...preset } };
  drawInstance(instance, 0); // quadro estático (também o estado de movimento reduzido)

  observeVisibility(host, {
    rootMargin: '200px 0px',
    onEnter: () => {
      visible.add(instance);
      syncTicker();
    },
    onLeave: () => {
      visible.delete(instance);
      syncTicker();
    },
  });
  return instance;
}

export function initLiquidMetal(root = document) {
  for (const host of qsa('[data-metal]', root)) {
    const preset = host.dataset.metal === 'badge' ? METAL_PRESETS.badge : METAL_PRESETS.button;
    createLiquidMetal(host, preset);
  }
}
