precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
varying mediump float vc;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;


void main(){
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 varCoord = a_TextureCoordinate.st;

 mediump vec3 v2 = vec3(oparam5, oparam6, oparam7);
 mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
 
 vc = 1.0 - a_Color;
 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal)) * 0.5 + 0.5;
}
