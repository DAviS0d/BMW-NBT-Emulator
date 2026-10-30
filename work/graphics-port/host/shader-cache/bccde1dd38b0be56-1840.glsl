precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord,cutout_coords,content_coords;
varying mediump vec4 varFade;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/* 
oparam0 ... alpha
oparam1 ... cutout for mould mapscale
oparam2 ... cutout for mould pill
oparam4 ... content alpha
oparam6 ... edge brightness
oparam7 ... edge brightness
*/

void main()
{
	/***** mirrored repeat for tegra *********/
    lowp vec4 color = texture2D(tex0, varCoord);
    
    
    /*********** cutout for moulds ***********************/
 	lowp vec3 texColor = texture2D(tex1, cutout_coords).rgb;
 	float alpha = dot(vec3(oparam1, oparam2, 1.), texColor);
	
	
	/******************** content *******************************/
    lowp vec4 content = texture2D(tex2, content_coords) * oparam4;
    
    
	vec4 basic = color * varFade;
    vec4 sampling = vec4(basic.rgb * (1.-content.a) + content.rgb, (basic.a - alpha) + content.a);
    gl_FragColor = sampling;
}
