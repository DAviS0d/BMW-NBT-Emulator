precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying mediump vec2 varCoord;
varying mediump vec2 varCoordDisplaced;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;
uniform mediump float oparam4;
uniform mediump float oparam5;
uniform mediump float oparam6;
uniform mediump float oparam7;


/*********************************************************************************
oparam0 = on/off
oparam1 = displace gradient
oparam2 = light edge translate
oparam3 = light intensity
***********************************************************************************/

void main(){

	// EDGES FADEOUT
	mediump vec4 edges_fadeout = texture2D(tex1,varCoord.xy); 
 
	// HIGHLIGHT BOTTOM
	mediump float light_edge = 1.0;
	mediump float lighten_factor = clamp(oparam3, 0.0, 0.5);
	mediump float light_interpolate = 0.0; //THIS WILL ALWAYS RETURN 0!!! ==> smoothstep(light_edge, light_edge+0.3, varCoord.y);
 
	// GRADIENT
 	mediump vec4 gradient =  texture2D(tex0, varCoordDisplaced);
 
	gl_FragColor.rgb = gradient.rgb;
	gl_FragColor.a =  edges_fadeout.r * oparam0;
}




