uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
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
 mediump float light_edge = clamp(oparam2, 0.0, 1.0);
 mediump float lighten_factor = clamp(oparam3, 0.0, 0.5);
 mediump float light_interpolate = smoothstep(light_edge, light_edge+0.3, varCoord.y);

 // GRADIENT DISPLACE		     	
 mediump vec2 coord_displaced = vec2 (varCoord.y + oparam1, varCoord.x);
 gl_FragColor =  texture2D(tex0, coord_displaced);
 
 gl_FragColor.rgb = (gl_FragColor.rgb + (light_interpolate * lighten_factor));
 gl_FragColor.a =  edges_fadeout.r;
 gl_FragColor.a *= oparam0;
}




