precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
varying float vc;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;


/*
oparam0 = alpha
oparam1 = reflection intensity
*/

void main(){
	vec4 base_color = texture2D(tex0, varCoord.yy);
   
    vec4 reflection = (1.0 + vc) * oparam1 * texture2D( tex1, ReflectDir.xy);
	vec4 antialiasing = texture2D( tex2, varCoord.yx);
	
    gl_FragColor = base_color;
	gl_FragColor.rgb += reflection.rgb;
	gl_FragColor.a = oparam0 * antialiasing.r;
}