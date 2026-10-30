precision highp float;

attribute         vec3 a_Position;
attribute mediump float a_VertexColor;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec2 a_TextureCoordinate1;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform         mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
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
void main(){
 //a_Position.z*=oparam3;
 
 mediump vec3 new_pos;
  
 mediump float angle = 0.2*cos(time);
  
 new_pos.x =  a_Position.x*cos( angle )-a_Position.y*sin( angle );
 new_pos.y =  a_Position.y*cos( angle )+a_Position.x*sin( angle );
 new_pos.z = a_Position.z;
 // scale
 
 
 
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 varCoord = a_TextureCoordinate.st;
// varCoord1 = a_TextureCoordinate1.st;
 mediump vec3 eyeDir = normalize(new_pos - EyePosModel);
 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));

}
