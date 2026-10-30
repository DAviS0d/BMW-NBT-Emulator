precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying vec3 ReflectDir;
varying vec4 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying mediump float invertedOparam1;
varying mediump float preMultiplyOparam0;
varying lowp vec4 lightColor;


#define color2float (12.)
#define RGBA(r,g,b,a) vec4( r*color2float,g*color2float,b*color2float,a*color2float )

/*
oparam0 = alpha
oparam1 = inner color (off for touch)
oparam2 = orange tint
oparam3 = flat orange
oparam4 = glow left right

UVINFO
x = 1-0 clockwise
y = radial 1inner 0outer
*/

void main(){
	
 //DIFFUSE	
 vec2 diffuse_coords = varCoord.zw;
 vec4 diffuse = texture2D(tex0,diffuse_coords );
 
 //REFLECTION
 vec3 rt = ReflectDir;//*ReflectDir*ReflectDir;
 //rt*=-1.;
 lowp vec4 refl = texture2D(tex3, rt.xy);
 lowp vec4 col = lightColor + diffuse*refl*preMultiplyOparam0;
 
 float ov1 = oparam1;
 float ov2 = invertedOparam1;
 
 gl_FragColor = (col+vec4(0.,0.,0.,col.a*ov2)) + oparam4*(texture2D(tex2,varCoord.st ));
 //gl_FragColor = diffuse;

}




