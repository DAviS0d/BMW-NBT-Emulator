precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/* 
oparam0 ... alpha
*/

void main()
{
	vec4 diffuse = texture2D(tex0,varCoord);
	float inner_mask = 1.-texture2D(tex2,varCoord).r;
	
	vec2 content_coords = vec2(gl_FragCoord.x + oparam7, gl_FragCoord.y) / vec2(oparam6, 480.);
	vec4 cursored = texture2D(tex1,content_coords); 

	gl_FragColor = vec4(mix(diffuse.rgb, cursored.rgb, (inner_mask*cursored.a)), diffuse.a);
	gl_FragColor.a *= oparam0;
}

// ORIGINAL BMW
// vec4 font = texture2D(tex1, vec2(gl_FragCoord.x + oparam7, gl_FragCoord.y) / vec2(oparam6, 480))
	