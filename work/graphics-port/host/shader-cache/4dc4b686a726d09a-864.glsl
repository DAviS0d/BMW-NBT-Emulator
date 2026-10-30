precision mediump float;

uniform sampler2D tex0;
varying mediump vec2 varCoord;
uniform mediump float oparam0,oparam1,oparam2;

/*
oparam0 ... opacity: 	0 = transparent 	| 1 = opaque
oparam1 ... selectable: 	0.6 = no 		| 1 = yes
oparam2 ... cursor state:	0 = focused		| 1 = unfocused
*/

void main()
{
	vec4 sample = texture2D(tex0, varCoord);
	vec3 co = vec3(0.4,0.7,0.7);
	vec3 co_bg = vec3(0.3,0.41,0.41);

	vec4 shading = vec4((mix(co_bg,co,sample.g))+ sample.r, sample.b * oparam1);
	gl_FragColor = oparam0 * shading;
}