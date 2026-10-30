uniform mat4 u_MVPMatrix;

attribute vec4 a_Position;
attribute vec2 a_TextureCoordinate;

varying vec2 vTexCoord;

void main()
{
    vec3 position = a_Position.xyz;

    gl_Position = u_MVPMatrix * a_Position;
    vTexCoord = vec2(a_TextureCoordinate.x, 1.-a_TextureCoordinate.y);
}