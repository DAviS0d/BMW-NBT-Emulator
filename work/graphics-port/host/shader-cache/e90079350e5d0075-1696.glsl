precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord,mask_coords;
varying mediump float vc,left;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha
adjust arch form in gradient
*/

void main()
{
	vec4 translation_mask = texture2D(tex1, mask_coords); 
	
	/** tl along gradient **/
	vec2 t_coords = varCoord;
	t_coords.x -= left * translation_mask.b;		//translate border to right

	vec4 cursor = texture2D(tex0, t_coords); 

	gl_FragColor = cursor;
	gl_FragColor.a *= oparam0;
}