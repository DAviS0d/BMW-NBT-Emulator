precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 glow_coords;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/* 
oparam0 ... alpha
oparam7 ... translate glow along x
*/

void main()
{
	/********** screenspace darkener *********/
	float darkener = (gl_FragCoord.y/880.)/4.0;
 
	/************** glow *******************/
	vec4 glow = texture2D(tex0, glow_coords);

	gl_FragColor = oparam0 * (glow - darkener);
}