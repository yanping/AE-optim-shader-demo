/**
 Shader inspired by Star Wars I pod-racing scene. Spent a long time tweaking shading and geometry, 
 I hope it runs reasonably well and looks good, I even tried to optimize this time :)
*/


mat3 rotx(float a) { mat3 rot; rot[0] = vec3(1.0, 0.0, 0.0); rot[1] = vec3(0.0, cos(a), -sin(a)); rot[2] = vec3(0.0, sin(a), cos(a)); return rot; }
mat3 roty(float a) { mat3 rot; rot[0] = vec3(cos(a), 0.0, sin(a)); rot[1] = vec3(0.0, 1.0, 0.0); rot[2] = vec3(-sin(a), 0.0, cos(a)); return rot; }
mat3 rotz(float a) { mat3 rot; rot[0] = vec3(cos(a), -sin(a), 0.0); rot[1] = vec3(sin(a), cos(a), 0.0); rot[2] = vec3(0.0, 0.0, 1.0); return rot; }
//mat3 transpose(in mat3 m) { mat3 mT; mT[0][0] = m[0][0]; mT[0][1] = m[1][0]; mT[0][2] = m[2][0]; mT[1][0] = m[0][1]; mT[1][1] = m[1][1]; mT[1][2] = m[2][1]; mT[2][0] = m[0][2]; mT[2][1] = m[1][2]; mT[2][2] = m[2][2]; return mT; }
const float PI = 3.14159265358;
const float PI2 = 3.14159265358 * 0.5;
const float TWO_PI = 3.14159265358 * 2.0;
float getShipRoll(float T);
float shadowEnv (in vec3 rp, in vec3 g, in vec3 ld);


// from IQ: https://iquilezles.org/articles/smin
float smin( float a, float b, float k )
{
    float h = clamp( 0.5+0.5*(b-a)/k, 0.0, 1.0 );
    return mix( b, a, h ) - k*h*(1.0-h);
}
// from IQ: https://iquilezles.org/articles/distfunctions
float sdBox( vec3 p, vec3 b )
{
  vec3 d = abs(p) - b;
  return min(max(d.x,max(d.y,d.z)),0.0) + length(max(d,0.0));
}

// plane looks down negative z axis. Orientation is controlled by rotation matrix.
float traceQuad(in vec3 ro, in vec3 rd, in vec3 pp, in vec2 sizeXY, in mat3 rt, in vec3 pivot )
{
    pp += rt * pivot;
    vec3 pn = rt * vec3(0.0, .0, -1.00);
    float a = dot(pp - ro, pn);
    float b = dot(rd, pn);
    float t = a / b;
    if (t < 0.0) return t;
    vec3 hitp = ro + rd * t;
    hitp = transpose(rt) * (hitp - pp); // to get to local coordinates
    if(abs(hitp.x) > sizeXY.x) return -1.;
    if(abs(hitp.y) > sizeXY.y) return -1.;
	return t;
}

// just a small helper function for bounding box tracing
float pmin(float m1, float m2)
{
    if (m1 >= 0.0 && m2 >= 0.0) { return min(m1, m2); } 
    return (m1 >= 0.0 && m2 < 0.0) ? m1 : m2;
}

// 6 quad checks
// returns ray enter and exit hitpoints.
// I'm using this as a bounding box to speedup the tracing process.
vec2 traceBox(in vec3 ro, in vec3 rd, in vec3 bp, in vec3 size, in mat3 rt)
{
    vec4 piv = vec4(size, 0.0);
    float f0 = traceQuad(ro, rd, bp, size.xy, rt, piv.wwz);
	float f1 = traceQuad(ro, rd, bp, size.xy * 1., rt, -piv.wwz);
	float f2 = traceQuad(ro, rd, bp, size.zy, rt * roty(PI2), piv.wwx);
	float f3 = traceQuad(ro, rd, bp, size.zy, rt * roty(PI2), -piv.wwx);
	float f4 = traceQuad(ro, rd, bp, size.xz, rt * rotx(PI2), -piv.wwy);
    float f5 = traceQuad(ro, rd, bp, size.xz, rt * rotx(PI2), piv.wwy);
        
    float m = pmin(f0, f1); m = pmin(m, f2); m = pmin(m, f3); m = pmin(m, f4); m = pmin(m, f5);
    if (m < 0.0) return vec2(m);
    
    vec2 ret = vec2(m, 1.0);
    if (f0 > 0. && f0 != ret.x) ret.y = f0;
    else if (f1 > 0. && f1 != ret.x) ret.y = f1;
    else if (f2 > 0. && f2 != ret.x) ret.y = f2;
    else if (f3 > 0. && f3 != ret.x) ret.y = f3;
    else if (f4 > 0. && f4 != ret.x) ret.y = f4;
    else if (f5 > 0. && f5 != ret.x) ret.y = f5;
        
    return ret;
}

// repeats space angularly.
vec2 repeatPolarAngle(in vec2 ar, float angle)
{	
    ar.x = mod(ar.x, angle);
    vec2 p = vec2(cos(ar.x), sin(ar.x)) * ar.y;
    return p;
}

// to polar coordinates
vec2 polar(in vec2 p)
{
    return vec2(atan(p.y, p.x), length(p));
}

// ship shape slices
const float slice = PI * 0.15;

vec2 g_rp_polar = vec2(0.0);
vec3 g_shipPos = vec3(0.0);
mat3 g_shipRotation = mat3(1.0);
vec3 g_hitp_local = vec3(0.0);
mat3 g_model_correction = mat3(1.0);
vec2 g_uv = vec2(0.0);
vec3 lightDir = normalize(vec3(.0, 15.0, -2.0));
float g_camT = 0.0; 
float g_shipT = 0.0;
vec3 g_hitp = vec3(0.0);

////////////////
// ship model
// basicly a box in a space that's repeated by angle
//////////////////
float map(in vec3 _rp)
{
    _rp -= g_shipPos;
    _rp = _rp * g_shipRotation;
    _rp = _rp * g_model_correction;
    g_rp_polar = polar(_rp.xz);
    g_hitp_local = _rp;
    
    // ship shape is made by repeating the space in pie-shape fashion
    vec2 rp_polar_real = polar(_rp.xz);
	vec2 rp_polar = abs(rp_polar_real);
    
    _rp.xz = repeatPolarAngle(rp_polar, slice);
    
    float m = sdBox( _rp, vec3(0.05, 0.0035, 0.05) * 4.0);
    float m3 = sdBox((_rp + vec3(-0.15, -0.015, 0.)), vec3(0.005, 0.015, 0.012) * vec3(6.0, 4.0, 10.0));
    
    // 2 boxes mixed gives nicer shape
	m = mix(m, m3, 0.1);
    // mixing with a sphere for a rounded shape
    m = mix(m, length(_rp - vec3(0.0, 0.05, 0.)) - .2, 0.2);
	return m;
}

// gradient
vec3 grad(in vec3 rp, float sharpness)
{
    vec2 off = vec2(sharpness, 0.0);
    vec3 g = vec3(map(rp + off.xyy) - map(rp - off.xyy),
                  map(rp + off.yxy) - map(rp - off.yxy),
                  map(rp + off.yyx) - map(rp - off.yyx));
    return normalize(g);
}


float g_rayExitDistance; // distance for exitting the bounding box of ship

// a bit hacky function to get the shading that I wanted.
float lobe(float d, float wrap)
{
    d = d + wrap / (1.0 + wrap);
    d /= sqrt(d);
    return d;
}

bool traceShip(in vec3 ro, in vec3 rp, in vec3 rd, inout vec4 outColor)
{
    bool hit = false;
    rp += rd * .3;
    float dist = 0.0;
    float fi = 0.0;
    float closest = 999.0;
    vec3 closestPos = vec3(0.0);
    
    for (int i = 0; i < 25; ++i)
    {
        fi = float(i);
        dist = map(rp);
        if (dist < closest)
        {
           closest = dist;
           closestPos = rp;
        }
        
        if(dist <= 0.00)
        {
            hit = true;
            break;
        }
        rp += rd * max(dist * .85, 0.005);
        float l = length(ro - rp);
        if (l > g_rayExitDistance) break;
    }
    
    // anti-aliasing the outer edges.
    float AA = dFdx(g_uv.x) * 2.;
    
    // early out if not close enough to edge
    if(closest > AA) { return false; }
    
    // few iterations for better quality if surface was penetrated a lot.
    for (int i = 0; i < 3; ++i)
    {
        rp += sign(dist) * max(abs(dist), 0.00001) * rd;
        dist = map(rp);
    }
    
    hit = hit || dist < 0.0;
    float rayLength = length(ro - rp);
    
    
    
    if(!hit) rp = closestPos;
    
    // depth test
	if (outColor.a < rayLength) return false;
    ////////////////////////////////////////////////
    //////////// UFO texturing and shading  ///////
    ///////////////////////////////////////////////
    
    float X = (PI * 0.05 + PI + g_rp_polar.x) / (2.0 * PI);
    float b = PI / slice * 4.0;
    X = floor(X * b);
    bool glass = false;
    
    vec4 albedo = (vec4(100,200,250, 0.0) / 256.0) * 0.9;

    vec4 color = vec4(0.0);
	float roughness = 0.15;
    float worness = 3.0;
    float refl = 0.05;
    
    if (g_hitp_local.y > 0.0 && g_hitp_local.y < 0.025 && (X == 0.0 || X == 1.0 || X == 27.0 || X == 26.0))
    {
        albedo.rgb = vec3(.9, .9, .9);
        glass = true;
    }
    
       
    vec3 yellow = vec3(.7, 0.2, 0.0);        
    if (g_hitp_local.y <= -0.01) albedo.rgb = vec3(.1, .1, .0);
    
    else if (g_hitp_local.y <= 0.006) albedo.rgb = yellow;
    else if (abs(g_rp_polar.x - 2.8) <= 0.02) albedo.rgb = yellow;
    else if (abs(g_rp_polar.x + 2.8) <= 0.02) albedo.rgb = yellow;
    else if (abs(g_rp_polar.x - .42) <= 0.08) albedo.rgb = yellow;
    else if (abs(g_rp_polar.x + .42) <= 0.08) albedo.rgb = yellow;
    else if (abs(g_rp_polar.x + .0) <= 0.08)  albedo.rgb = yellow;

    bool engine = (X >= 12.0 && X <= 15.0);
    if (g_hitp_local.y > -0.01 && g_hitp_local.y < 0.005 && engine)
    {
        color.rgb += (vec3(.5) + 0.35 * sin(abs(g_shipT * getShipRoll(g_shipT) * .03) )) ;
    }

    vec3 g = grad(rp, 0.0025);
    
    // Bump
    if(!glass)
    {
        vec2 bmpUv = g_hitp_local.xz;
        
        vec3 bump = roughness * texture(iChannel2, bmpUv * 5.5).rgb;
        
        float bm = 75.0;
        float damage = sin(bmpUv.y * bm * 0.6) * sin(bmpUv.x * bm) * 0.5;
        damage += sin(bmpUv.y * bm * 0.3) * sin(bmpUv.x * bm * 0.3);
        
        damage = clamp(damage, 0.0, 1.0);
        roughness += worness * roughness * damage;
        bump += roughness * texture(iChannel2, g_hitp_local.yz * 5.5).rgb;
        albedo = mix(albedo, vec4(0.6, 0.2, 0.0, .0), roughness * .8);
        g = g + bump * 1.;
        g = normalize(g);
    }

    float d = dot(g, lightDir);
    d = clamp(d, 0.0, 1.0);
    d = lobe(d, 0.1);
    color += albedo * d;
	
    // spec
    float sp = glass ? 13.0 : 80.0;
    vec3 H = normalize(-rd + lightDir);
    float Sd = dot(H, g);
    Sd = clamp(Sd, 0.001, 1.0);
    Sd = lobe(Sd, 0.);
    Sd = pow(Sd, sp) * .2;
	
    vec3 envColor = texture(iChannel3, reflect(rd, g)).rgb;
    color.rgb += glass ? 0.7 * envColor : envColor * max(0.0, (1.0 - roughness)) * refl;
    
    // fres
    float SCL = 4.; 
    float PWR = 10.0;
    
    float Fd = dot(rd, g);
    Fd = min(1.0, 1.0 + Fd) * 0.5;
    Fd = lobe(Fd, 0.25);
    
    float F = SCL * pow(Fd, PWR);
    vec3 FCol = vec3(0.2, 0.12, 0.04);
	color.rgb = mix(color.rgb, FCol, min(F, 1.0) );
    color += vec4(Sd);
    
    float colMix = smoothstep(AA, 0.0, closest);
    
    float sh = shadowEnv(rp, vec3(0.0, .2, 0.0), lightDir);
   	color.rgb *= mix(1.0, sh, 0.75);
    outColor = mix(outColor, color, colMix);
    outColor.a = rayLength;
    g_hitp = rp;
    
    return hit;
}


// 
bool doShip(in vec3 rp, in vec3 rd, inout vec4 color)
{
    vec3 ro = rp;
    vec2 hitBox = traceBox(ro, rd, g_shipPos + vec3(0.0, 0.01, 0.0), vec3(0.24, 0.05, 0.21), g_shipRotation);
    if (hitBox.x <= 0.) return false;
    
    // bug fix to where 2 seams meet
    g_rayExitDistance = max (hitBox.y, 2.5);
    
    bool hit = traceShip(ro, rp, rd, color);
    //if(hit) color += vec4(0.1);
    return hit;
}

/////////////////////////////////////
///////// ENVIRONMENT ///////////////
//////////////////////////////////////
float ENV_P = 0.05; // scale for fbm texture uv
float ENV_B = .3; // multiplier for strength of fbm
vec3 bgFadeCol = vec3(1.2, .95, .6) * 0.45;

// clouds
float fbmHI (in vec2 uv)
{
	float f = texture(iChannel2, uv).r * 0.5;    
	f += texture(iChannel2, uv * 2.0).r * 0.25;    
	f += texture(iChannel2, uv * 4.0).r * 0.25 * 0.5;
	f += texture(iChannel2, uv * 8.0).r * 0.25 * 0.5 * 0.5;
	f += texture(iChannel2, uv * 16.0).r * 0.25 * 0.5 * 0.5 * 0.5;
    return f;
}

// walls
float fbm (in vec2 uv)
{
	float f = texture(iChannel2, uv).r * 0.75;    
	f += texture(iChannel2, uv * 7.0).r * 0.25 * 0.5;
    return f;
}

// walls
float fbmLO (in vec2 uv)
{
	float f = texture(iChannel2, uv).r * 0.75;    
    return f;
}

float g_fbm;
vec3 _mapRP;

// path curving
float getPathOffset(float x)
{
    float offset =  sin(x * 0.1) * 2.0 + sin(x * 0.05) * 3. + cos(x * 0.2) * 1.0;
    return offset * 1.7;
}

float getMapHeight(float x)
{
    return 0.5 + (sin(x * 0.05 + sin(x * 0.3))) * 0.5;
}

// vertical layer size
const float layerSize = .95;

// valley width
float valleyWidth = 7.;
float g_shadowSharpness = 0.16;

float _mapEnv(in vec3 rp)
{
    rp.z += getPathOffset(rp.x);
    float sgnZ = rp.z > 0.0 ? 1.0 : -1.0;
    
    float sx2 = sin(rp.x * 0.25);
    float sx3 = sin(rp.x * 0.0125);
    ///////////////
    // tilt of valley
    float tilt = (-.2 + smoothstep(-.5, .5, sx3)); 
    g_shadowSharpness = clamp(tilt, 0.025, 0.26); // hack to get shadows look good
    // curves on layers
    float c = sx3 + sx2 * 0.5 + sin(rp.x) * sgnZ * 0.15;
    rp.y += c;
    // layers
    float fy = fract(rp.y / layerSize);
    float l =  floor(rp.y / layerSize) * tilt + smoothstep( 0.0, 0.85, fy) * tilt;
    rp.z = min(0.0, -abs(rp.z) - valleyWidth + l);
    
    // negative space inside
    float m = 0.006 * dot(rp.zy, rp.zy) - .5;
    m = max(-m, sdBox(_mapRP, vec3(10000.0, -c + 5., 10000.0)));
    m = smin(m, sdBox(_mapRP + vec3(0.0, 1.0, 0.0),vec3(20000.0, 1.0, 20000.0)), .2);
	return m;        
}


float groundDetail(in vec3 rp)
{
   float F = fbmLO(rp.xz * .01);
   float amount = 0.25 + sin(rp.x * 0.05) * 0.2;
   F = smoothstep(amount, amount + .08, F);
   return smoothstep(.2, 0.0, rp.y) * F;
}

float mapEnvLO(in vec3 rp)
{
    _mapRP = rp + getMapHeight(rp.x);
    g_fbm = fbmLO (abs(rp.xz) * ENV_P) * ENV_B;
    float d = groundDetail(_mapRP);
    rp.xy += g_fbm;
	
    return _mapEnv(rp);
}


float mapEnv(in vec3 rp)
{
    _mapRP = rp + getMapHeight(rp.x);
    g_fbm = fbm  (abs(rp.xz) * ENV_P) * ENV_B;
    
    float d = groundDetail(_mapRP);
    _mapRP.y += d * .35 * g_fbm;
    rp.xy += g_fbm;
    return _mapEnv(rp);
}

// environment gradient
vec3 gradEnv(in vec3 rp, float sharpness)
{
    vec2 off = vec2(sharpness, 0.0);
    vec3 g = vec3(mapEnv(rp + off.xyy) - mapEnv(rp - off.xyy),
                  mapEnv(rp + off.yxy) - mapEnv(rp - off.yxy),
                  mapEnv(rp + off.yyx) - mapEnv(rp - off.yyx));
    return normalize(g);
}

vec4 tex3D( sampler2D tex, in vec3 p, in vec3 n )
{
    vec4 c1 = texture(tex, p.xy);
    vec4 c2 = texture(tex, p.yz);
    vec4 c3 = texture(tex, p.xz);
    
    vec4 color = abs(dot(n, vec3(0.0, 0.0, 1.0))) * c1;
    color += abs(dot(n, 	vec3(1.0, 0.0, 0.0))) * c2;
    color += abs(dot(n, 	vec3(0.0, 1.0, 0.0))) * c3;
    return clamp(color, 0.0, 1.0);
}


// tint on the ground texture
vec4 groundTint = vec4(0.35, 0.25, 0.1, 0.0) * 3.0;

// shadows and occlusion
float shadowEnv (in vec3 rp, in vec3 g, in vec3 ld)
{
	rp += g * 0.03;
    const int stps = 10;

    float s = 1.0;
    float occ = 0.0;
    for (int i = 1; i < stps; ++i)
    {
        float stp = .015 * float(i * i);
	    rp += ld * stp;
        float d = mapEnv(rp);
        occ += clamp(d/stp, .0, 1.0) * (1./float(i));
        s = min(s, clamp(mapEnv(rp) / stp, 0.0, 1.0));
    }
    occ /= 2.0;
    
    s = smoothstep(0.0, g_shadowSharpness, s);
    s = min(s, occ);
	return min(s, 1.);
}

float getCurvature(in vec3 rp, in vec3 g)
{
   vec3 gw = fwidth(g);
   vec3 pw = fwidth(rp);
   float wfcurvature = length(gw) / length(pw);
   return smoothstep(0.0, 12., wfcurvature);        
}

vec3 g_groundHitp = vec3(0.0);

bool doEnv(in vec3 rp, in vec3 rd, inout vec4 color)
{
    vec3 ro = rp;
    float dist = 0.0;
    bool hit = false;
    float closest = 999.0;
    vec3 closestPos = vec3(0.0);
    float AA = 1.0 * dFdx(g_uv).x;
    float travelled = 0.0;
    
    for (int i = 0; i < 45; ++i)
    {
        dist = mapEnvLO(rp);
        if (dist < closest)
        {
            closest = dist;
            closestPos = rp;
        }
        
        if (dist < 0.0)
        {
            hit = true;
            break;
        }
        float lg2 = log2(1.0 + travelled * 15.0);
        float stp = max(0.01 * lg2, dist * (.9 + lg2));
        rp += rd * stp;
        travelled += stp;
        
        if (travelled > 150.0)
        {
            break;
    	}
    }
    
    // detail steps
    for (int i = 0; i < 35; ++i)
    {
        float D = dist * 0.5 * log2(1.0 + travelled);
        travelled += D;
        
        rp += sign(D) * max(abs(D), 0.001) * rd;
        dist = mapEnv(rp);
        hit = hit;// || hitDetail;
    }
    
    closestPos = rp;
    AA *= travelled * 30.0;
	AA = smoothstep(AA, .0, closest);
    
    float depth = travelled;
    hit = hit || AA > .0;
    
    if (depth < color.a)
    {
        rp = closestPos;
        g_groundHitp = ro + rd * depth;    
        
        if (hit)
        {
	        color.a = depth;
        }
        vec3 g = gradEnv(closestPos, 0.05);
        vec3 tc = (tex3D(iChannel1, closestPos * 0.15, g) * groundTint).rgb;
        float luma = dot ( vec3(0.2126,0.7152, 0.0722), vec3(fbm(closestPos.xz * 2.1)));
        float m = groundDetail(closestPos);
        
		float texLuma = dot ( vec3(0.2126,0.7152, 0.0722), tc); 
        vec3 sand = mix(tc, mix(1., luma, 0.3) * vec3(1., .7, .4), m);
        tc = mix(tc, sand, .5);
        
        //////////////////////
        // some curvature details (ice)
        float c1 = getCurvature(closestPos, g);
        vec3 p2 = closestPos + vec3(.05, .0, .0);
        vec3 g2 = gradEnv(p2, .05);
        float c2 = getCurvature(p2, g2);
        float curvature = 0.35 * (c1 + c2);
		
        tc = mix(tc, vec3(1.0), smoothstep(2., .0, rp.y) * curvature);
        float sh = shadowEnv(rp, g2, lightDir);
        tc *= mix(1.0, sh, 0.81);
        
        float d = dot(g, lightDir);
        d = clamp(d, 0.01, 1.0);
        d = lobe(d, 0.4);
        
        color.rgb = mix(color.rgb, tc * d, AA);
        
    }
    
    g_hitp = rp;
	return hit;  
}

mat3 lookat(vec3 from, vec3 to)
{
    vec3 f = normalize(to - from);
    vec3 _tmpr = normalize(cross(f, vec3(0.0, .999, 0.0)));
    vec3 u = normalize(cross(_tmpr, f));
    vec3 r = normalize(cross(u, f));
    return mat3(r, u, f);
}
///////////////////////////////////////////////
////////   Ship and camera orientation   //////
///////////////////////////////////////////////
vec3 getCamDirection(float T);
vec3 getCamPos(float T);

vec3 getShipPos(float T, float o)
{
    g_shipT = o + T + 1.5;
    vec3 cp =  vec3(g_shipT, .6 + sin(g_shipT*.15) * 0.2, .0);
    cp.z -= getPathOffset(g_shipT);
    return cp;
}

vec3 getShipVelocity(float T)
{
    vec3 p1 = getShipPos(T, .0);
	vec3 p2 = getShipPos(T, 1.0);
	return (p2 - p1);
}
vec3 getShipDirection(float T)
{
    return normalize(getShipVelocity(T));
}

float getShipRoll(float T)
{
    vec3 dirAtT = getShipDirection(T + 1.5);
    float roll = (cross(dirAtT, getShipDirection(T + .0))).y * 10.0;
    return clamp(roll, -PI2, PI2);
}

mat3 getShipRotation(float T)
{
    vec3 dirAtT = getShipDirection(T + 1.5);
    mat3 fw = lookat(vec3(0.0), dirAtT);
    return fw * rotz(-getShipRoll(T));
}

bool g_camStill = false;
const float SEQ_LENGTH = 250.0;
const float CAM_DRIVE_TIME = 50.0;

void checkCamStill(float T)
{
    g_camStill = mod(T, SEQ_LENGTH) < CAM_DRIVE_TIME;
}

float getCamCurvature(float T)
{
    vec3 dirAtT = getCamDirection(T);
    mat3 fw = lookat(vec3(0.0), dirAtT);
    return (cross(dirAtT, getCamDirection(T - 1.1))).y;
}


vec3 getCamPos(float T)
{
    if (g_camStill) T = floor(T / SEQ_LENGTH) * SEQ_LENGTH + CAM_DRIVE_TIME / 2.0;
    float y =  .5 + (.3 * sin(T * 0.05));
	vec3 cp = vec3(0.0);
    if (g_camStill) 
    {
    	cp =  vec3(T, y - .15, .1);
    }
    else
    {
    	cp =  vec3(T,y, .0);
		cp.x += sin(T * 0.05) * .5;
    }
   	cp.z -= getPathOffset(cp.x);
	return cp;    
}

vec3 getCamDirection(float T)
{
    
    vec3 p1 = getCamPos(T - 2.);
    if(g_camStill) p1 = getCamPos(T);
    
    vec3 p2 = getShipPos(T, 0.0);
    return normalize(p2 - p1);
}

mat3 getCamRotation(float T)
{
    mat3 fw = lookat(vec3(0.0), getCamDirection(T));
    float roll = getCamCurvature(T) * 8.0;
    roll = clamp(roll, -PI2, PI2);
    if(g_camStill) roll = 0.0;
    return fw * rotz(-roll);
}

void doSky(in vec3 ro, in vec3 rd, inout vec3 col)
{

    float skyH = 120.0;
    float dif = skyH - ro.y;
    float cloudSpeed = iTime * 0.01;
    vec3 rp = ro + (rd * dif * (1.0 / rd.y));
    vec2 uv = vec2(rp.xz * 0.0001);
    float f = fbmHI(cloudSpeed * vec2(1.0, 0.0) + uv);
    f = smoothstep(0.0, 0.8, f);
    
    float f2 = fbmHI(cloudSpeed * vec2(1.0, 0.4) + uv * 2.0);
    f = mix(f, f2, 0.5);
    col = mix(col, vec3(f - smoothstep(1., 2.5, f + f2)), f);
}


void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    
    g_camT = 100.0 + mod(iTime, 900.0) * 10.0;
    checkCamStill(g_camT);
    
    g_shipRotation = getShipRotation(g_camT);
    g_model_correction = roty(-PI2);
	
    vec2 uv = fragCoord.xy / iResolution.xy;
    uv -= vec2(0.5);
    uv.y /= iResolution.x / iResolution.y;
	g_uv = uv;
    vec2 im = 2.0 * ((iMouse.xy / iResolution.xy) - vec2(0.5));
    
    /////////////
    /// Camera
    //////////////
    vec3 rp = getCamPos(g_camT);
    g_shipPos = getShipPos(g_camT, 0.0);

	vec3 rd = normalize(vec3(uv, .4));
    mat3 lkAtMat = getCamRotation(g_camT);
    
    rd = normalize(lkAtMat * rd);    
    fragColor.rgb = vec3(0.0);
	fragColor.a = 9999.0;
    ///////////////////////////
    /// BG mountains + sky  ///
    ///////////////////////////

    vec3 depthFade = mix(fragColor.rgb, bgFadeCol, min(1.0, pow(fragColor.a * 0.02, 1.)));
    fragColor.rgb = depthFade;
    
    // sky colors and mountains
    if (rd.y > 0.0)
    {
	    vec2 polar = vec2(PI + atan(rd.z, rd.x), 1.0);
    	float H = sin(polar.x * 20.0) * 0.2;
    	H += sin(polar.x * 1.0) * 0.4;
    	H += sin(polar.x * 5.0) * 2.0;
    	H += sin(polar.x * .4) * 0.25;
        
	    vec3 grp = rp + rd * 1000.0;
	    float mTop = -25.0;
    	float mFade = smoothstep(0.0, 5000. * dFdx(g_uv).x, (grp.y + mTop) - H * 10.0);
        fragColor.rgb = (1.0 - vec3(mFade)) * bgFadeCol;
        vec3 skyBottom = vec3(.5, .6, .8) * 2.;
        vec3 skyTop = vec3(0.2, 0.3, 0.7) * 2.1;
        fragColor.rgb += mix(skyBottom, skyTop, smoothstep(0.0, 0.6, rd.y)) * mFade;
    }
    
	// Environment
    bool env = doEnv(rp, rd, fragColor);
    // Ship    
    bool shipHit = doShip(rp, rd, fragColor);
    
    // ship shadow
    if (!shipHit)
    {
        vec3 dif = (g_shipPos - g_groundHitp);
        float d = dot(normalize(dif), vec3(0.0, 1.0, 0.0));
        d = clamp(d, 0.0, 1.0);
        float x = pow(length(dif * 20.), .7) * (1.0 - d);
        x = clamp(x, 0.0, 1.0);
        fragColor.rgb = mix(fragColor.rgb, x * fragColor.rgb, 0.5);
    }
    
    
    // clouds
    if(!env && !shipHit && rd.y > 0.0)
    {
        doSky(rp, rd, fragColor.rgb);
    }

    ////////////////////////////
    // data for motion blur   //
    /////////////////////////////
    
	// the pixel at (0, 0) reads previous frame ray direction from pixel (1, 0) 
    // pixel at (1, 0) stores ray direction with "time stamp"
    float tStamp = mod(float(iFrame), 100.0);
    if(fragCoord.y < 1.0)
    {
        if(fragCoord.x < 1.0)
        {
            // check value from pixel next to this
	        vec4 stored = texture(iChannel0, vec2(1.5, 0.5) / iChannelResolution[0].xy, -100.0 );
            if (stored.a != tStamp)
            {
                // store value if it's older than current frame to this pixel
                fragColor = stored;
            }
        }
        else if (fragCoord.x < 2.0)
        {
	        fragColor.rgb = vec3(0.0, 0.0, 1.0) * lkAtMat;
            fragColor.a = tStamp;
        }
        // camera matrix information
        else if (fragCoord.x < 3.0) fragColor.rgb = lkAtMat[0];
        else if (fragCoord.x < 4.0) fragColor.rgb = lkAtMat[1];
        else if (fragCoord.x < 5.0) fragColor.rgb = lkAtMat[2];
        
    }
}
