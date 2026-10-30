precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord,loadCoord;
varying mediump vec3 co;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	vec4 sample = texture2D(tex0, varCoord);
	float load = fract(loadCoord.x - oparam1);
	load -= smoothstep(0.95, 1.0, load);
	load *= sample.b;
	
	vec3 shading = (co + sample.r) + load;
	float opacity = sample.g * oparam0;

	gl_FragColor = vec4(shading, opacity); 
}