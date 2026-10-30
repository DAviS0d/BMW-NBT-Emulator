attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal;
uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;

varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
varying mediump float ambient;
varying mediump float vcolors;

void main(){
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	varCoord = a_TextureCoordinate.st;
	
	mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
	ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
	
	//AMBIENT
	ambient = clamp((dot(vec3(0.,0.,1.), a_Normal)),0.6 ,1.);
	vcolors = a_Color;
}
