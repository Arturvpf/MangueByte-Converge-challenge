/**
 * Helpers de WebGL compartilhados pelos shaders.
 */

export function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Falha ao compilar shader: ${log}`);
  }
  return shader;
}

/**
 * Cria um programa e devolve `{ program, uniforms }`, onde `uniforms` é um
 * mapa nome -> location para todos os uniforms ativos.
 */
export function createProgram(gl, vertexSource, fragmentSource) {
  const program = gl.createProgram();
  gl.attachShader(program, compileShader(gl, gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource));
  gl.bindAttribLocation(program, 0, 'aPosition');
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`Falha ao linkar programa: ${gl.getProgramInfoLog(program)}`);
  }

  const uniforms = {};
  const count = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < count; i++) {
    const { name } = gl.getActiveUniform(program, i);
    uniforms[name] = gl.getUniformLocation(program, name);
    // arrays aparecem como "uPal[0]"; também registra o nome base
    if (name.endsWith('[0]')) uniforms[name.slice(0, -3)] = uniforms[name];
  }
  return { program, uniforms };
}

/**
 * Triângulo que cobre a tela inteira (3 vértices, sem índice).
 * Mesmo truque do original: [-1,-1, 3,-1, -1,3].
 */
export function createFullscreenTriangle(gl) {
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  return buffer;
}

/** "#rrggbb" -> [r, g, b] em 0..1 (sRGB). */
export function hexToRgb(hex) {
  const value = parseInt(hex.replace('#', ''), 16);
  return [(value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255];
}

/** sRGB -> linear (para render targets SRGB8_ALPHA8, como no original). */
export function srgbToLinear([r, g, b]) {
  const convert = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return [convert(r), convert(g), convert(b)];
}
