precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord,archCoord;
varying float sample_width,radius,opacity;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
oparam1 ... active switch: 	0 = inactive  0.25 = active  0.5 = second column 
*/

void main()
{
	  	/* arch equations */
  		float circle_mask = length(archCoord);
  		float arch = smoothstep(radius + sample_width, radius, circle_mask);

	vec4 sample = texture2D(tex0, varCoord);
	sample.a *= arch;
	
	gl_FragColor = oparam0 * sample;
}