precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec3 co_btm,co_tp;
varying mediump vec2 varCoord,archCoord;
varying float sample_width,radius;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
oparam1 ... div switch:  	0 = none  		0.25 = top  	0.5 = bottom  	0.75 = both
oparam2 ... active switch: 	0 = inactive 	1 = active
oparam3 ... translate arch mask along x save hardcoded when final
*/

void main()
{
	  	/* arch equations */
  		float circle_mask = length(archCoord);
  		float arch = smoothstep(radius + sample_width, radius, circle_mask);

	vec4 sample = texture2D(tex0, varCoord);
	vec3 shading = mix(co_btm, co_tp, sample.b);
	float opacity = sample.r * arch;
	gl_FragColor = vec4(shading, opacity * oparam0);
}