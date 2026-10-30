precision highp float;

attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position;
uniform highp mat4 MVPMatrix;
varying mediump vec2 varCoord;

void main(){
	
	varCoord = a_TextureCoordinate.st;
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
}
