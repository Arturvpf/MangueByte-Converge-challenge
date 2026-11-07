/**
 * Fluted Swirl — fundo animado do hero (e do CTA do rodapé).
 *
 * Port do componente "Fluted Swirl" (script-017). Dois passes WebGL2:
 *   1. scene: campo de "swirl" (3 camadas de seno distorcidas) renderizado
 *      numa textura sRGB com metade da resolução;
 *   2. glass: vidro canelado (flutes) que refrata a cena, separa cor nas
 *      bordas (aberração) e tinge as arestas com uma paleta + brilho.
 *
 * GLSL copiado do bundle. Divergência: o campo de "tinta" que segue o
 * cursor (simulação 128x128 na CPU) não foi portado; uFieldOn fica 0.
 */

import { onTick } from '../lib/ticker.js';
import { createProgram, hexToRgb, srgbToLinear } from '../lib/webgl.js';
import { observeVisibility, prefersReducedMotion } from '../lib/dom.js';

/* --- Presets --------------------------------------------------------------
   DEFAULTS = objeto `Cs`; HERO = `Bs` (Cs + paleta/ângulo/frequência). */
const DEFAULTS = {
  colorA: '#000000',
  colorB: '#f0f0f0',
  detail: 2.7,
  swirlSpeed: 1,
  blend: 84,
  shape: 'rounded',
  angle: 31,
  frequency: 16,
  softness: 1,
  refraction: 4.9,
  aberration: 0.46,
  lightAngle: -90,
  highlight: 0.12,
  highlightSoftness: 0,
  highlightColor: '#ffffff',
  waveAmplitude: 0.06,
  waveFrequency: 1.5,
  glassSpeed: 0.15,
  grain: 0.05,
  grainBias: 2,
  toneMin: 0,
  toneMax: 0.9,
  edgeLow: 0.3,
  edgeHigh: 0.885,
  midCurve: 0.89,
  palette: ['#FFE0D6', '#E4B67C', '#5FC3EE', '#718EE8'],
  paletteGain: 1.76,
  paletteEdge: 0.263,
};

export const PRESETS = {
  hero: {
    ...DEFAULTS,
    colorA: '#000000',
    colorB: '#F0F0F0',
    palette: ['#C4BFB7', '#A6591E', '#8F8F8F', '#9BAACF', '#3C5385'],
    aberration: DEFAULTS.aberration * 0.9,
    angle: 31,
    frequency: 10,
    refraction: 4.9,
  },
  // Adaptação: mesmo componente com faixa tonal escura para o CTA do rodapé.
  dark: {
    ...DEFAULTS,
    colorA: '#000000',
    colorB: '#5a5a5a',
    palette: ['#8F8F8F', '#C4BFB7', '#9BAACF'],
    paletteGain: 1.2,
    frequency: 12,
    angle: 52,
    toneMax: 0.75,
  },
};

/* --- Shaders --------------------------------------------------------------- */

const VERTEX = `#version 300 es
layout(location = 0) in vec2 aPosition;
out vec2 vUv;
void main() {
  vUv = vec2(aPosition.x * 0.5 + 0.5, 0.5 - aPosition.y * 0.5); // y para baixo, como a fonte
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;

const TO_SRGB = `
vec3 toSrgb(vec3 c) {
  c = max(c, 0.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}`;

const SCENE_FRAGMENT = `#version 300 es
precision highp float;
in vec2 vUv;
uniform float uTime;
uniform float uDetail;
uniform float uBias;
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform vec2 uTone;      // x: mais escuro, y: mais claro (fração de A até B)
uniform vec2 uThreshold; // suavidade da borda do swirl
uniform float uMid;      // curva de meio-tom
out vec4 outColor;

float flowLayers(vec2 uv, float detail, float t) {
  float f1 = detail;
  vec2 d1 = vec2(
    uv.x + sin(uv.y * f1 * 1.7 + t * 0.8) * 0.12 + cos(uv.x * f1 * 0.9 - t * 0.5) * 0.05,
    uv.y + cos(uv.x * f1 * 1.3 - t * 0.6) * 0.12 + sin(uv.y * f1 * 1.1 + t * 0.7) * 0.05);
  float p1 = sin(d1.x * f1 * 2.1 + d1.y * f1 * 1.8 + t * 0.4);
  float f2 = detail * 2.1;
  vec2 d2 = vec2(
    d1.x + cos(d1.y * f2 * 2.7 - t * 0.45) * 0.07 + sin(d1.x * f2 * 1.9 + t * 0.6) * 0.04,
    d1.y + sin(d1.x * f2 * 2.3 + t * 0.65) * 0.07 + cos(d1.y * f2 * 1.6 - t * 0.4) * 0.04);
  float p2 = cos(d2.x * f2 * 1.4 - d2.y * f2 * 1.9 + t * 0.35);
  float f3 = detail * 3.7;
  vec2 d3 = vec2(
    d2.x + sin(d2.y * f3 * 1.8 + t * 0.85) * 0.04 + cos(d2.x * f3 * 1.3 - t * 0.55) * 0.025 + sin((d2.x + d2.y) * f3 * 0.7 + t * 0.9) * 0.02,
    d2.y + cos(d2.x * f3 * 1.6 - t * 0.75) * 0.04 + sin(d2.y * f3 * 1.1 + t * 0.5) * 0.025 + cos((d2.x + d2.y) * f3 * 0.8 - t * 0.95) * 0.02);
  float p3 = sin(d3.x * f3 * 1.1 + d3.y * f3 * 1.5 - t * 0.55);
  return p1 * 0.45 + p2 * 0.35 + p3 * 0.2;
}

void main() {
  float pat = flowLayers(vUv, uDetail, uTime);
  float k = pow(smoothstep(uThreshold.x, uThreshold.y, pat * 0.5 + 0.5 + uBias), uMid);
  vec3 col = mix(uColorA, uColorB, k);
  col *= sin(uTime * 2.5 + pat * 8.0) * 0.015 + 1.0;
  // Mantém o resultado numa faixa neutra entre as duas cores.
  vec3 span = uColorB - uColorA;
  vec3 rel = (col - uColorA) / max(abs(span), vec3(1e-4)) * sign(span + 1e-6);
  col = uColorA + span * (uTone.x + clamp(rel, -0.2, 1.2) * (uTone.y - uTone.x));
  outColor = vec4(max(col, 0.0), 1.0); // linear; o alvo sRGB codifica na escrita
}`;

const GLASS_FRAGMENT = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uScene;
uniform float uAspect;
uniform float uFluteT;
uniform float uAngle;
uniform float uFreq;
uniform float uSoft;
uniform float uWaveAmp;
uniform float uWaveFreq;
uniform float uRefr;
uniform float uAberr;
uniform int uPalN;
uniform vec3 uPal[8];
uniform float uPalGain;
uniform float uPalEdge;
uniform vec3 uShape;
uniform float uLightAngle;
uniform float uHighlight;
uniform float uHlSoft;
uniform vec3 uHlColor;
uniform float uGrain;
uniform float uGrainBias;
uniform vec2 uViewport;
out vec4 outColor;
${TO_SRGB}
const float PI = 3.14159265359;

vec2 mirrorUv(vec2 uv) {
  vec2 m = mod(abs(uv), 2.0);
  return vec2(m.x >= 1.0 ? 2.0 - m.x : m.x, m.y >= 1.0 ? 2.0 - m.y : m.y);
}
vec3 scene(vec2 uv) {
  vec2 m = mirrorUv(uv);
  return texture(uScene, vec2(m.x, 1.0 - m.y)).rgb;
}
float hash12(vec2 p) {
  uvec2 u = floatBitsToUint(p * vec2(141421356.0, 2718281828.0));
  return float((u.x ^ u.y) * 3141592653u) / 4294967295.0;
}

// Uma amostra do flute: refração + separação de cor, mais o termo de brilho.
vec4 fluteSample(float pos, float cosA, float sinA) {
  float cell = (fract(pos) - 0.5) * 2.0;
  float absCell = max(abs(cell), 1e-4);
  float slope = sign(cell) * pow(absCell, mix(uShape.x, uShape.y, uSoft));
  float halfCell = 0.5 / max(uFreq, 0.001);
  float refrU = -slope * uRefr * halfCell;
  vec2 ruv = vec2(vUv.x + refrU * cosA / uAspect, vUv.y + refrU * sinA);
  float chrU = refrU * uAberr * 0.5;
  vec2 off = vec2(chrU * cosA / uAspect, chrU * sinA);

  vec3 sC = scene(ruv);
  float e = dot(scene(ruv + off) - scene(ruv - off), vec3(0.2126, 0.7152, 0.0722));
  float x = (1.0 - clamp(e / uPalEdge, -1.0, 1.0)) * 0.5 * float(uPalN - 1);
  int i0 = int(x);
  vec3 tint = mix(uPal[i0], uPal[min(i0 + 1, uPalN - 1)], x - float(i0));
  vec3 col = max(sC + abs(e) * uPalGain * tint, 0.0);

  float slopeSq = min(slope * slope, 1.0);
  float nz = sqrt(1.0 - slopeSq);
  float half_ = uLightAngle * PI / 360.0;
  float nDotH = max(slope * sin(half_) + nz * cos(half_), 0.0);
  float shininess = exp2(8.0 - uHlSoft * 7.0);
  float fresnel = 0.04 + 0.96 * pow(1.0 - nz, 5.0);
  return vec4(col, pow(nDotH, shininess) * fresnel * uHighlight);
}

void main() {
  float r = uAngle * PI / 180.0;
  float cosA = cos(r);
  float sinA = sin(r);
  vec2 ac = vec2((vUv.x - 0.5) * uAspect, vUv.y - 0.5);
  float u = ac.x * cosA + ac.y * sinA;
  float v = -ac.x * sinA + ac.y * cosA;
  float wave = sin(v * uWaveFreq * PI * 2.0 + uFluteT * 2.0) * uWaveAmp;
  float pos = (u + uShape.z * wave) * uFreq + uFluteT;

  // Antialias só perto da borda entre flutes (4 sub-amostras).
  float w = fwidth(pos);
  float f = fract(pos);
  vec4 s;
  if (min(f, 1.0 - f) < w * 1.5) {
    s = (fluteSample(pos - w * 0.375, cosA, sinA) + fluteSample(pos - w * 0.125, cosA, sinA)
       + fluteSample(pos + w * 0.125, cosA, sinA) + fluteSample(pos + w * 0.375, cosA, sinA)) * 0.25;
  } else {
    s = fluteSample(pos, cosA, sinA);
  }
  vec3 col = s.rgb + uHlColor * s.a;

  if (uGrain > 0.0) {
    float n = hash12(vUv * uViewport);
    float bright = clamp(dot(col, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
    col += (n * 2.0 - 1.0) * pow(1.0 - bright + 1e-6, uGrainBias) * (uGrain * 0.1);
  }
  outColor = vec4(toSrgb(col), 1.0);
}`;

/* --- Conversões de cor (iguais às funções hs/_s do original) -------------- */

const toLinear = (hex) => srgbToLinear(hexToRgb(hex));

/** Paleta como "direção de tinta": (2c - 1) com 95% da luminância removida. */
function paletteUniform(colors) {
  const list = colors.slice(0, 8);
  const values = new Float32Array(24);
  list.forEach((hex, index) => {
    const rgb = hexToRgb(hex).map((c) => c * 2 - 1);
    const luma = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
    for (let k = 0; k < 3; k++) values[index * 3 + k] = rgb[k] - luma * 0.95;
  });
  return { count: list.length, values };
}

const SHAPES = { bars: [16, 4, 0], waves: [8, 3, 1], rounded: [8, 3, 0] };

/* --- Renderer -------------------------------------------------------------- */

class FlutedSwirlRenderer {
  constructor(canvas) {
    const gl = canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: false,
    });
    if (!gl) throw new Error('WebGL2 indisponível');

    this.canvas = canvas;
    this.gl = gl;
    this.scene = createProgram(gl, VERTEX, SCENE_FRAGMENT);
    this.glass = createProgram(gl, VERTEX, GLASS_FRAGMENT);

    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    this.sceneTexture = gl.createTexture();
    this.framebuffer = gl.createFramebuffer();
    this.size = { w: 0, h: 0, sceneW: 0, sceneH: 0, cssW: 1, cssH: 1 };
  }

  /** Buffer limitado a `maxPixels`; cena em meia resolução (mínimo 64px). */
  resize(cssW, cssH, dpr, maxPixels = 4.2e6) {
    const { gl, size } = this;
    cssW = Math.max(1, cssW);
    cssH = Math.max(1, cssH);
    let ratio = Math.min(Math.max(dpr, 1), 2);
    if (cssW * cssH * ratio * ratio > maxPixels) ratio = Math.sqrt(maxPixels / (cssW * cssH));

    const w = Math.max(1, Math.round(cssW * ratio));
    const h = Math.max(1, Math.round(cssH * ratio));
    const sceneW = Math.max(64, Math.round(cssW * 0.5));
    const sceneH = Math.max(64, Math.round(cssH * 0.5));
    Object.assign(size, { cssW, cssH });

    if (w !== size.w || h !== size.h) {
      this.canvas.width = w;
      this.canvas.height = h;
      Object.assign(size, { w, h });
    }
    if (sceneW !== size.sceneW || sceneH !== size.sceneH) {
      gl.bindTexture(gl.TEXTURE_2D, this.sceneTexture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.SRGB8_ALPHA8, sceneW, sceneH, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.sceneTexture, 0);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      Object.assign(size, { sceneW, sceneH });
    }
  }

  /** @param {number} time segundos  @param {typeof DEFAULTS} p parâmetros */
  draw(time, p) {
    const { gl, size } = this;
    gl.bindVertexArray(this.vao);

    // Passe 1: cena -> textura
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.viewport(0, 0, size.sceneW, size.sceneH);
    gl.useProgram(this.scene.program);
    const s = this.scene.uniforms;
    gl.uniform1f(s.uTime, time * p.swirlSpeed);
    gl.uniform1f(s.uDetail, p.detail);
    gl.uniform1f(s.uBias, (p.blend - 50) * 0.006);
    gl.uniform3fv(s.uColorA, toLinear(p.colorA));
    gl.uniform3fv(s.uColorB, toLinear(p.colorB));
    gl.uniform2f(s.uTone, p.toneMin, p.toneMax);
    gl.uniform2f(s.uThreshold, p.edgeLow, p.edgeHigh);
    gl.uniform1f(s.uMid, p.midCurve);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    // Passe 2: vidro canelado -> tela
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, size.w, size.h);
    gl.useProgram(this.glass.program);
    const g = this.glass.uniforms;
    const palette = paletteUniform(p.palette);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.sceneTexture);
    gl.uniform1i(g.uScene, 0);
    gl.uniform1f(g.uAspect, size.cssW / size.cssH);
    gl.uniform1f(g.uFluteT, -time * p.glassSpeed);
    gl.uniform1f(g.uAngle, p.angle);
    gl.uniform1f(g.uFreq, p.frequency);
    gl.uniform1f(g.uSoft, p.softness);
    gl.uniform1f(g.uWaveAmp, p.waveAmplitude);
    gl.uniform1f(g.uWaveFreq, p.waveFrequency);
    gl.uniform1f(g.uRefr, p.refraction);
    gl.uniform1f(g.uAberr, p.aberration);
    gl.uniform1i(g.uPalN, palette.count);
    gl.uniform3fv(g.uPal, palette.values);
    gl.uniform1f(g.uPalGain, p.paletteGain);
    gl.uniform1f(g.uPalEdge, p.paletteEdge);
    gl.uniform3fv(g.uShape, SHAPES[p.shape] ?? SHAPES.rounded);
    gl.uniform1f(g.uLightAngle, p.lightAngle);
    gl.uniform1f(g.uHighlight, p.highlight);
    gl.uniform1f(g.uHlSoft, p.highlightSoftness);
    gl.uniform3fv(g.uHlColor, toLinear(p.highlightColor));
    gl.uniform1f(g.uGrain, p.grain);
    gl.uniform1f(g.uGrainBias, p.grainBias);
    gl.uniform2f(g.uViewport, size.w, size.h);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}

/* --- Componente -------------------------------------------------------------- */

/**
 * Liga o shader a um <canvas>. Anima só quando visível (IntersectionObserver
 * com margem de 100px, como o original); com movimento reduzido desenha um
 * único quadro estático.
 */
export function createFlutedSwirl(canvas, preset = PRESETS.hero) {
  let renderer;
  try {
    renderer = new FlutedSwirlRenderer(canvas);
  } catch (error) {
    console.warn('[fluted-swirl]', error.message);
    canvas.remove();
    return null;
  }

  const params = { ...preset };
  let time = 0;
  let stopTicking = null;

  const fit = () => {
    const rect = canvas.getBoundingClientRect();
    const isPhone = window.matchMedia('(max-width: 809.98px)').matches;
    renderer.resize(rect.width, rect.height, Math.min(window.devicePixelRatio || 1, isPhone ? 1.5 : 2));
  };

  const drawStill = () => {
    fit();
    renderer.draw(time, params);
  };

  const play = () => {
    if (stopTicking || prefersReducedMotion()) return;
    stopTicking = onTick((_elapsed, delta) => {
      time += Math.min(delta / 1000, 0.1);
      renderer.draw(time, params);
    });
  };

  const pause = () => {
    stopTicking?.();
    stopTicking = null;
  };

  new ResizeObserver(drawStill).observe(canvas);
  drawStill();
  observeVisibility(canvas, { rootMargin: '100px 0px', onEnter: play, onLeave: pause });

  return { play, pause, params };
}
