precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord,varCoord1;
varying mediump vec3 co;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;


/*
oparam0 ... opacity
oparam1 ... 0 = inactive  | 1 = active
oparam2 ... light animation
*/

void main()
{
	vec4 sample = texture2D(tex0, varCoord);
	float light = texture2D(tex1, varCoord1).g;
	
	vec3 shading = co - sample.b;
	shading += light * sample.g * 1.5;

	float opacity = sample.a;
	gl_FragColor = vec4(shading, oparam0 * opacity);
}