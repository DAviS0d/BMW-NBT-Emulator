precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
varying mediump float antialiasing,radial_gradient;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
*/

void main()
{
	vec3 color = vec3(0.5, 0.5, 0.5);
	float fadeout = texture2D(tex0, varCoord.yx).a - radial_gradient;  //adjust fadeout via alpha channel of gradient texture
	
	gl_FragColor = vec4(color, antialiasing * fadeout);
	gl_FragColor.a *= oparam0;
}