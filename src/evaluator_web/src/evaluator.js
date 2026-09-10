// WebGL2 Evaluator Core for Playwright Candidate Evaluation

import { GPUTimer } from './gpuTimer.js';
import { VERTEX_SHADER_SRC, wrapShadertoyCode } from './shadertoyCompat.js';

const canvas = document.getElementById('eval-canvas');
const gl = canvas.getContext('webgl2', {
  preserveDrawingBuffer: true,
  antialias: false,
  alpha: false,
  powerPreference: 'high-performance'
});

if (!gl) {
  console.error('WebGL2 context creation failed');
}

const timer = new GPUTimer(gl);

// Quad Geometry Setup
const positionBuffer = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
  -1, -1,  1, -1, -1,  1,
  -1,  1,  1, -1,  1,  1
]), gl.STATIC_DRAW);

// 1x1 White Texture Fallback
const dummyTex = gl.createTexture();
gl.bindTexture(gl.TEXTURE_2D, dummyTex);
gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255, 255, 255, 255]));
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);

// 1x1 White Cubemap Fallback
const dummyCubeTex = gl.createTexture();
gl.bindTexture(gl.TEXTURE_CUBE_MAP, dummyCubeTex);
const cubePixel = new Uint8Array([255, 255, 255, 255]);
for (let face = 0; face < 6; face++) {
  gl.texImage2D(gl.TEXTURE_CUBE_MAP_POSITIVE_X + face, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, cubePixel);
}
gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

function compileShader(gl, type, src) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(info || 'Shader compile error');
  }
  return shader;
}

// Window Preflight check for Python evaluator
window.checkPreflight = async function() {
  if (!gl) {
    return { success: false, error: 'WebGL2 context creation failed' };
  }

  const debugExt = gl.getExtension('WEBGL_debug_renderer_info');
  const renderer = debugExt
    ? gl.getParameter(debugExt.UNMASKED_RENDERER_WEBGL)
    : gl.getParameter(gl.RENDERER);

  return {
    success: true,
    renderer: renderer,
    timerQuery: timer.isSupported,
    webglVersion: gl.getParameter(gl.VERSION)
  };
};

// Window Shader Evaluator API
window.evaluateShader = async function(options) {
  const {
    code,
    sampleTimes = [0.0, 1.5, 3.0, 4.5, 6.0],
    warmupFrames = 25,
    timedSamples = 10,
    channelTypes = ['2d', '2d', '2d', '2d']
  } = options;

  let vertexShader, fragmentShader, program;
  const fullFragmentSrc = wrapShadertoyCode(code, channelTypes);

  try {
    vertexShader = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER_SRC);
    fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fullFragmentSrc);

    program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const info = gl.getProgramInfoLog(program);
      throw new Error(info || 'Program link error');
    }
  } catch (err) {
    return {
      compileOk: false,
      compileError: err.message
    };
  }

  gl.useProgram(program);

  // Bind Samplers 0-3 (support both 2D textures and Cubemaps)
  for (let i = 0; i < 4; i++) {
    gl.activeTexture(gl.TEXTURE0 + i);
    const isCube = fullFragmentSrc.includes(`samplerCube iChannel${i};`);
    if (isCube) {
      gl.bindTexture(gl.TEXTURE_CUBE_MAP, dummyCubeTex);
    } else {
      gl.bindTexture(gl.TEXTURE_2D, dummyTex);
    }
    const loc = gl.getUniformLocation(program, `iChannel${i}`);
    if (loc !== null) gl.uniform1i(loc, i);
  }

  // Attribute and Uniform Locations
  const aPos = gl.getAttribLocation(program, 'a_position');
  const uRes = gl.getUniformLocation(program, 'iResolution');
  const uTime = gl.getUniformLocation(program, 'iTime');
  const uMouse = gl.getUniformLocation(program, 'iMouse');
  const uFrame = gl.getUniformLocation(program, 'iFrame');

  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.enableVertexAttribArray(aPos);
  gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
  gl.viewport(0, 0, canvas.width, canvas.height);

  const timingResults = [];
  const capturedFrames = [];
  let frameCount = 0;

  for (const timeSec of sampleTimes) {
    // 1. Warmup draws
    for (let w = 0; w < warmupFrames; w++) {
      if (uRes !== null) gl.uniform3f(uRes, canvas.width, canvas.height, 1.0);
      if (uTime !== null) gl.uniform1f(uTime, timeSec);
      if (uMouse !== null) gl.uniform4f(uMouse, 0, 0, 0, 0);
      if (uFrame !== null) gl.uniform1i(uFrame, frameCount++);

      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }

    // Capture screenshot data URL for quality/FLIP comparison
    const framePng = canvas.toDataURL('image/png');
    capturedFrames.push({
      time: timeSec,
      dataUrl: framePng
    });

    // 2. Timed benchmark draws
    for (let s = 0; s < timedSamples; s++) {
      if (uRes !== null) gl.uniform3f(uRes, canvas.width, canvas.height, 1.0);
      if (uTime !== null) gl.uniform1f(uTime, timeSec);
      if (uMouse !== null) gl.uniform4f(uMouse, 0, 0, 0, 0);
      if (uFrame !== null) gl.uniform1i(uFrame, frameCount++);

      let elapsedMs = null;
      if (timer.isSupported) {
        const q = timer.createQuery();
        timer.beginQuery(q);
        gl.drawArrays(gl.TRIANGLES, 0, 6);
        timer.endQuery(q);
        gl.flush();
        elapsedMs = await timer.pollResult(q);
      } else {
        // Fallback performance.now() CPU-GPU fence timing
        const t0 = performance.now();
        gl.drawArrays(gl.TRIANGLES, 0, 6);
        gl.finish();
        elapsedMs = performance.now() - t0;
      }

      if (elapsedMs !== null && !isNaN(elapsedMs) && elapsedMs > 0) {
        timingResults.push(elapsedMs);
      }
    }
  }

  // Cleanup shaders and program
  gl.deleteProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);

  // Calculate Median GPU Time
  timingResults.sort((a, b) => a - b);
  const medianGpuTimeMs = timingResults.length > 0
    ? timingResults[Math.floor(timingResults.length / 2)]
    : 16.67;

  return {
    compileOk: true,
    gpuTimeMs: medianGpuTimeMs,
    sampleCount: timingResults.length,
    frames: capturedFrames
  };
};
