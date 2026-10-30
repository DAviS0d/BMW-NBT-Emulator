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

//#define vec4 mediump vec4
//#define vec2 mediump vec2
//#define vec3 mediump vec3
//#define float mediump float


/**************************************************************************************
oparam0 = alpha fade
oparam4 = font x translate 
oparam5 = font y translate 
oparam6 = font width 
oparam7 = font height
**********************************************************************************/

void main(){

 // FONT SHADOW
 mediump float start_x = oparam4;
 mediump float start_y = oparam5;
 mediump float stretch_factor_x = oparam6;
 mediump float stretch_factor_y = oparam7;
 mediump float step_x = 1. / 1280.;
 mediump float step_y = 1./ 480.;

 #define LOOKUP(xx,yy) texture2D(tex0, vec2(start_x + varCoord.x * stretch_factor_x + step_x * xx, start_y + varCoord.y * stretch_factor_y + step_y * yy))

 //BLUR  
 mediump vec4 font = (	 LOOKUP( 0., 0. )
  				        +LOOKUP( 2.5, 0. )
  				        +LOOKUP( 0., 2.5 )
  				        +LOOKUP(-2.5, 0. )
  				        +LOOKUP( 0.,-2.5 )
  				        +LOOKUP( 1.25, 1.25 )
  				        +LOOKUP(-1.25, -1.25 )
  				        +LOOKUP(-1.25, 1.25 )
  				        +LOOKUP( 1.25,-1.25 )
  				        * (1./9.));
  				
 gl_FragColor.rgb = vec3(0.0,0.0,0.0);
 gl_FragColor.a = font.a; 
 gl_FragColor.a *= oparam0;
}