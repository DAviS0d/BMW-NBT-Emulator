precision mediump float;

varying mediump vec2 vTexCoord;
uniform sampler2D tex0;
uniform sampler2D tex1;
uniform float fillFactor;

void main()
{
	vec2 flowOutDirection = vec2(0.54,-0.30);
	vec4 mainColor = texture2D(tex0, vec2(vTexCoord.x,vTexCoord.y) + (flowOutDirection * (1.0 - fillFactor)));
	vec4 maskColor = texture2D(tex1, vTexCoord.xy);
    gl_FragColor = mainColor * maskColor.r;
}