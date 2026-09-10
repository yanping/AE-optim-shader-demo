// Shadertoy Compatibility Preamble and Screen Quad Vertex Shader

export const VERTEX_SHADER_SRC = `#version 300 es
in vec2 a_position;
out vec2 v_uv;

void main() {
    v_uv = a_position * 0.5 + 0.5;
    gl_Position = vec4(a_position, 0.0, 1.0);
}
`;

export function wrapShadertoyCode(glslBody, channelTypes = null) {
  const effectiveTypes = channelTypes ? [...channelTypes] : ['2d', '2d', '2d', '2d'];
  while (effectiveTypes.length < 4) effectiveTypes.push('2d');

  // If channelTypes was not explicitly specified, auto-detect cubemap sampling patterns
  if (!channelTypes) {
    for (let i = 0; i < 4; i++) {
      const cubeRegex = new RegExp(`texture\\s*\\(\\s*iChannel${i}\\s*,\\s*(?:reflect\\s*\\(|vec3\\s*\\(|(?:rd|rayDir|viewDir|eyeDir)\\s*[,\\)])`);
      if (cubeRegex.test(glslBody)) {
        effectiveTypes[i] = 'cubemap';
      }
    }
  }

  const channelDecls = [0, 1, 2, 3].map(i => {
    const isCube = effectiveTypes[i] === 'cubemap';
    return `uniform ${isCube ? 'samplerCube' : 'sampler2D'} iChannel${i};`;
  }).join('\n');

  let preamble = `#version 300 es
precision highp float;
precision highp int;

uniform vec3 iResolution;
uniform float iTime;
uniform float iTimeDelta;
uniform float iFrameRate;
uniform vec4 iMouse;
uniform int iFrame;

${channelDecls}
uniform vec3 iChannelResolution[4];

out vec4 fragColor;
`;

  let cleanedBody = glslBody;
  if (cleanedBody.includes('#version')) {
    cleanedBody = cleanedBody.replace(/#version\s+\d+(\s+es)?/g, '');
  }

  // Strip EVOLVE-BLOCK markers if present in payload
  cleanedBody = cleanedBody.replace(/^[ \t]*(?:#|\/\/|\/\*)[ \t]*EVOLVE-BLOCK-(?:START|END)[^\n]*\n?/gm, '');

  if (!cleanedBody.includes('out vec4 fragColor') && !cleanedBody.includes('fragColor')) {
    cleanedBody = cleanedBody.replace(/\bgl_FragColor\b/g, 'fragColor');
  }

  let mainWrapper = '';
  if (!cleanedBody.includes('void main()') && cleanedBody.includes('mainImage')) {
    mainWrapper = `
void main() {
    mainImage(fragColor, gl_FragCoord.xy);
}
`;
  }

  return preamble + '\n' + cleanedBody + '\n' + mainWrapper;
}
