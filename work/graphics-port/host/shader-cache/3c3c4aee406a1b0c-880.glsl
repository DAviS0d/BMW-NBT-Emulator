precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform mediump float oparam0,oparam1;

/*
oparam0 ... opacity: 	0 = transparent 	| 1 = opaque
oparam1 ... selectable: 	0.6 = no 		| 1 = yes
*/

void main()
{
	vec4 sample = texture2D(tex0, varCoord);
	gl_FragColor = vec4(sample.rgb, sample.a * oparam1); 
	gl_FragColor.a *= oparam0;
}