precision mediump float;
uniform sampler2D tex0,tex1;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

//alpha= oparam0
//skala rotation= oparam4

void main(){
	vec4 fadeout = texture2D(tex1, varCoord.xy);
	
	vec2 ssl = varCoord.xy;
    ssl.x += oparam4+0.124;
	ssl.x *= 0.5;
 	vec4 skala = texture2D(tex0, fract(ssl));
	gl_FragColor.rgba = skala.rgba;
 	gl_FragColor.a *= fadeout.r;

	 gl_FragColor.a *= oparam0;
}