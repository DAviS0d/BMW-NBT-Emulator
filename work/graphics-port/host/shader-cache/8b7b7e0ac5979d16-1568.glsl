precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/* 
oparam0 ... alpha
oparam1 ... active / inactive
*/

void main()
{
	vec4 material = texture2D(tex0, varCoord);
	vec4 material_ia = texture2D(tex1, varCoord);
	
	material = mix(material, material_ia, oparam1);
	
	gl_FragColor = material;
	gl_FragColor.a *= oparam0;
}