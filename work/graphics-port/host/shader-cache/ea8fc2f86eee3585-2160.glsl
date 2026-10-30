precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec3 co_tp,co_hl;
varying mediump vec2 varCoord,archCoord;
varying float sample_width,radius;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
oparam1 ... active switch   0 = inactive   | 1 = active
oparam2 ... bottom translate
*/

void main()
{
	  	/* arch equations */
  		float circle_mask = length(archCoord);
  		float arch_cutaway_most = smoothstep(radius + sample_width, radius, circle_mask);
  		float r2 = radius - 2.;
  		float arch_cutaway_hl = smoothstep(r2 + sample_width, r2, circle_mask);


	vec4 sample = texture2D(tex0, varCoord);
	vec3 shading = mix(co_tp, co_hl, oparam1 * sample.r) - sample.b;
	float opacity = mix(sample.g * 0.7, sample.g, oparam1);
	opacity *= mix(arch_cutaway_most, arch_cutaway_hl, sample.r); //highlight above edge
	
	gl_FragColor = vec4(shading, opacity * oparam0);
}