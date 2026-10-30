precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha
oparam1 ... inactive on
oparam2 ... active on
*/

void main()
{	
	vec4 inactive = texture2D(tex0, varCoord);
	vec4 active = texture2D(tex1, varCoord);
 
	gl_FragColor =  inactive * oparam1 + 
					active * oparam2;
	gl_FragColor.a *= oparam0;				
}