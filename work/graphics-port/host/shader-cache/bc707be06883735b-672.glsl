precision mediump float;

varying vec2 vTexCoord;
uniform sampler2D tex0;

uniform float u_ConstAlpha;

void main()
{
    gl_FragColor = texture2D(tex0, vec2(vTexCoord.x, vTexCoord.y));
	
	// only darken color, do not touch the alpha value!!!
	gl_FragColor.rgb *= u_ConstAlpha;
}
