attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
//varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord, varCoord1;


uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying mediump float ambient;
varying mediump float specular;

varying vec3 nrml;

void main(){
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 varCoord = a_TextureCoordinate.st;
 varCoord1 = a_TextureCoordinate1.st;
 mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
 mediump vec3 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
 
 //AMBIENT
 ambient = clamp((dot(vec3(0.,0.,1.), a_Normal)),0.6 ,1.);
 
 //SPECULAR
 //mediump vec3 specular_light = normalize(vec3(.3,-.4, 1.));
 mediump vec3 specular_light = normalize(vec3(0.3,0.2, 0.5));
 //mediump float specular_vec = clamp(dot(specular_light, normalize(MVPMatrix*vec4(a_Normal,1))),0. ,1.);
 mediump float specular_vec = clamp(dot(specular_light, ReflectDir),0. ,1.); //
 specular = pow(specular_vec * 1.06, 22.);
 nrml = a_Normal;

}
