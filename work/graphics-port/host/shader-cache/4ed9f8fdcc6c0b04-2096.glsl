precision highp float;

attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position;
uniform highp mat4 MVPMatrix;
varying mediump vec2 varCoord;
varying mediump vec3 co;


void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	varCoord = a_TextureCoordinate;
	co = vec3(1.,1.,1.);
}
