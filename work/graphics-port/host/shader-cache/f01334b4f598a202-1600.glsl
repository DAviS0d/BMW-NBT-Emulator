precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... opacity: 	0 = transparent 	| 1 = opaque
oparam1 ... selectable: 	0.6 = no 		| 1 = yes
oparam2 ... cursor state:	0 = focused		| 1 = unfocused
*/

void main()
{
	vec4 sample = texture2D(tex0, varCoord);
	float color_max = max(sample.r, max(sample.b, sample.g));
	float color_min = min(sample.r, min(sample.b, sample.g));
	vec3 color_med = vec3(color_max - color_min);
	vec3 color_desat = mix(sample.rgb, color_med, 1. - oparam1);
	
	gl_FragColor = vec4(color_desat, sample.a * oparam1); 
	gl_FragColor.a *= oparam0;
}