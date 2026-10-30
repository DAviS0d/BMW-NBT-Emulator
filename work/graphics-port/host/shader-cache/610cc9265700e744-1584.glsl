precision mediump float;
uniform sampler2D tex0,tex1,tex2;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

//alpha= oparam0
//pointer rotation= oparam4

void main(){

	vec4 bg = texture2D(tex0, varCoord.xy);
	vec4 fadeout = texture2D(tex2, varCoord.xy);


	vec2 ssl = varCoord.xy;
    ssl.x += oparam4 ;
	ssl.x *= 1.;
 	vec4 pointer = texture2D(tex1, ssl);
 	gl_FragColor = bg;	
	gl_FragColor.rgba += pointer.rgba;
 	gl_FragColor.a *= fadeout.r;

	gl_FragColor.a *= oparam0;
	 
}