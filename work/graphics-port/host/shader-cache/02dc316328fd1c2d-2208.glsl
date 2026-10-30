precision highp float;

attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position;
uniform highp mat4 MVPMatrix;
varying mediump vec2 varCoord;
uniform mediump float oparam0,oparam1,oparam2;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	varCoord = a_TextureCoordinate.st;
	varCoord.x *= 0.5;
	varCoord.x += oparam2 * 0.5;
}