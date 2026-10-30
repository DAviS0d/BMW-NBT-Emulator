precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
varying float edge_alpha;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
*/

void main()
{
	vec4 glow = texture2D(tex1, varCoord.yx);
	float fadeout = texture2D(tex0, varCoord).a;
	
	gl_FragColor = glow * fadeout;
	gl_FragColor.a *= oparam0 * edge_alpha; 
}