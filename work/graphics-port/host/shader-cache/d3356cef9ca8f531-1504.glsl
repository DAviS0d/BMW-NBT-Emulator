precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
varying mediump float antialiasing;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
oparam1 ... rotate
oparam2 ... offset
oparam3 ... fadeout reduction
*/


void main()
{
	
	float fadeoout = varCoord.y - oparam3;
	gl_FragColor.rgb = vec3(1.,1.,1.);
	gl_FragColor.a = oparam0 * antialiasing * fadeoout; 						
}