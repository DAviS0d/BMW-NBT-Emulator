attribute highp   vec3 a_Position;
attribute mediump float a_VertexColor;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec2 a_TextureCoordinate1;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump mat4 ModelWorld4;
uniform mediump mat4 VPMatrix;
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
 
 vec4 vertexPos = vec4( ( a_Position.xyz), 1.);
 vertexPos.xz += 0.5;//shift space to 0..1
 vertexPos.x *= oparam1*oparam5; // scale to new size
 vertexPos.z *= oparam2*oparam6; // scale to new size
 
 vertexPos = ModelWorld4 * vertexPos;
 
 vertexPos.x -= 0.5/oparam5 - oparam3;
 vertexPos.z -= 0.5/oparam6;
 vertexPos.z += 1./oparam6 - (oparam4 + oparam2);
 

 gl_Position = VPMatrix *  vertexPos;
 gl_Position /= gl_Position.w;


 varCoord = a_TextureCoordinate.st;
 mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
}
