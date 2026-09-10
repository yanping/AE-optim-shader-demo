float rand(vec2 co){
    return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
}

void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    
    vec2 uv = fragCoord.xy / iResolution.xy;
    fragColor.rgb = texture(iChannel1, uv).rgb;
    fragColor.rgb = smoothstep(0.0, 1.0, fragColor.rgb);
    fragColor.rgb += 0.006 * 0.5 * (rand(uv + iTime) + rand(uv + vec2(0.1) + iTime));
    fragColor.rgb = pow(fragColor.rgb, vec3(1.0 / 2.2));
    
    
}
