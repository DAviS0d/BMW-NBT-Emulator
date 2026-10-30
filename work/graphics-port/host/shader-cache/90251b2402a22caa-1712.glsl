precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
varying float edge_alpha;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
oparam1 ... grow
*/

void main()
{
	/********* for growth ********************/
	float growth_coords = varCoord.x + oparam1;
	float growth_faded = smoothstep(0.99,1.01,growth_coords);
	
	
	/******** active ********************************************/
	vec4 measure_scale = growth_faded * texture2D(tex0, varCoord);

	gl_FragColor = measure_scale;
	gl_FragColor.a *= oparam0 * edge_alpha; 
} 






