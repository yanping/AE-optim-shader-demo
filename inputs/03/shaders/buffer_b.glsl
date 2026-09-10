vec4 getTexColor(vec2 uv)
{
    return texture(iChannel0, uv);
}

void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    
    vec2 uv = fragCoord.xy/iResolution.xy;

    vec4 texColor = getTexColor(uv);
    
    vec3 prevCamD = texture(iChannel0, vec2(0.5, 0.5) / iChannelResolution[0].xy, -100.0 ).rgb;

    mat3 lkAt;
    lkAt[0] = texture(iChannel0, vec2(2.5, 0.5) / iChannelResolution[0].xy, -100.0 ).rgb;
    lkAt[1] = texture(iChannel0, vec2(3.5, 0.5) / iChannelResolution[0].xy, -100.0 ).rgb;
    lkAt[2] = texture(iChannel0, vec2(4.5, 0.5) / iChannelResolution[0].xy, -100.0 ).rgb;
    
    float stpX = (1.0 / iResolution.x);
    float stpY = (1.0 / iResolution.y);
    
    vec3 dif = prevCamD * transpose(lkAt);
    dif.x *= -1.0;
    dif *= log2(1.0 + dot(dif, dif) * 1000.0);
    vec3 color = texColor.rgb * 1.0;
    
    const int stps = 10;
    float dist = max( (log2(1.0 + texColor.a * 200.0) ) - 4.0, 0.0);
    float depth = min( dist, 250.0);
    float ld = length(dif);
    
    float w = 1.0;
    for (int i = 1; i < stps; ++i)
    {
        vec2 _uv = uv - dif.xy * depth * float(i) * fwidth(uv) * .35;
        
        if (_uv.x >= 0.0 && _uv.x <= 1.0 && _uv.y >= 0.0 && _uv.y <= 1.0)
        {
            float wt = 1.0 / (float(i) + 1.);
            w += wt;
	        color += getTexColor(_uv).rgb * wt;
        }
    }
    
    color /= w;
    fragColor.rgb = color;
}
