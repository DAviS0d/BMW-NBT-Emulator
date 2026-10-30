precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha
oparam1 ... both inactive
oparam2 ... left active
oparam3 ... right active
*/

void main()
{	 
	vec4 off = texture2D(tex0, varCoord);
	vec4 one = texture2D(tex1, varCoord);
	vec4 two = texture2D(tex2, varCoord);
 
 	gl_FragColor = 	off * oparam1 + 
					one * oparam2 + 
					two * oparam3 ;
 	gl_FragColor.a *= oparam0;				
}