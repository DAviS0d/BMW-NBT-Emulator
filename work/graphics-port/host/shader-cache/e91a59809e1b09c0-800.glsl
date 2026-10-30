precision mediump float;

varying mediump vec2 vTexCoord;
uniform sampler2D tex0;
uniform sampler2D tex1;
uniform float fillFactor;

void main()
{
	vec2 fillDirection = vec2(0.34,-0.27);
	vec4 mainColor = texture2D(tex0, vec2(vTexCoord.x-0.34,vTexCoord.y+0.275) + (fillDirection * fillFactor));
	vec4 maskColor = texture2D(tex1, vTexCoord.xy);
    gl_FragColor = mainColor * maskColor.r;
}