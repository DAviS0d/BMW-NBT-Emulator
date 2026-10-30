precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
varying vec2 varCoord2;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

//#define vec4 mediump vec4
//#define vec3 mediump vec3
//#define vec2 mediump vec2
//#define float mediump float
#define my_floor(x) step(0.3, x)

void main(){
 
 //TOP BOTTOM CUTOUT (via y-coords): top having 0.0, bottom 0.25, left/right 1.0
  float on_off = 1.0 - varCoord.y;
  float top = step(on_off, 0.1);
  float bottom = step(on_off, 0.3)-top;
 
 on_off += (top * oparam1) + (bottom * (oparam2 * 0.75)) ;
 on_off = clamp(on_off, 0.0, 1.0);
 
 //SHADOW
  vec3 color = vec3(1.,1.,1.);
  float factor = smoothstep( 0.0,1.0,( varCoord.x * oparam5 ) - oparam4 );
  vec4 shadow_color = mix(
 							      vec4(color.rgb, 0.0),
 						          vec4(color.rgb, 0.7),
 							      factor);
 

 gl_FragColor = shadow_color;
 gl_FragColor.a = shadow_color.a * my_floor(on_off); 
 gl_FragColor.a = gl_FragColor.a * oparam0;
 //gl_FragColor.rgb *= vec3((1.-varCoord2.x)+1.)*oparam3;
 
 
 gl_FragColor.rgb *= 1.-gl_FragColor.a;//vec3( smoothstep(  0.5,1.0, 1.-varCoord2.x ))*oparam6; //vec3((1.-varCoord2.x)+1.)*oparam3; 
 //gl_FragColor.rgb = gl_FragColor.aaa;
 //gl_FragColor.a = 1.;
}





				