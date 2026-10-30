precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 archCoord,varCoord,varCoord1;
varying float sample_width,radius;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha 
oparam1 ... top off on
oparam2 ... bottom off on

uv info:
varCoord1.x = left half
*/

void main()
{
	  	/* arch equations */
  		float circle_mask = length(archCoord);
  		float arch_for_translation = smoothstep(radius - sample_width, radius, circle_mask);
	
	float bend_left_side = mix(varCoord.x, arch_for_translation, varCoord1.y);
	vec4 sample = texture2D(tex0, vec2(bend_left_side, varCoord.y));

	float shadow = mix( mix(sample.r, sample.g, oparam1), sample.b, oparam2);
		
	gl_FragColor = vec4(0.,0.,0., shadow * oparam0);
}




















/*

precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 archCoord,varCoord;
varying float sample_width,radius;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;



void main()
{

  		float circle_mask = length(archCoord);
  		float inner_mask = smoothstep(radius - sample_width, radius, circle_mask);
		float shadow = varCoord.x - (varCoord.y * inner_mask);		

		
	gl_FragColor = vec4(0.,0.,0., shadow * oparam0);
}*/